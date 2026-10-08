"""Real pypdf re-save workload for long PDF names; no expected answers, timing or grading in the worker.

run(case, size, seed) builds deterministic PDFs (stdlib generator below), opens each with pypdf.PdfReader, copies every
page into a pypdf.PdfWriter, writes it, and re-reads the written file. It returns digests of the names, contents and
written name tokens the library produced.
Cases: "resave:<docs>" and "tagged:<docs>" (size = how many times the producer re-encoded the names; 3 pages per doc,
"tagged" also uses the name as a marked-content tag and parses each input page's content stream),
"special:<pages>" (size = name length in characters), "boundary:<length>" (size = pages),
"brokenlen:<start>" (size = pages; content streams without /Length).
Input contract: every '#' in a name is followed by exactly two hexadecimal digits.
"""
import argparse
import hashlib
import io
import json
import re

# ---- fixture generator (stdlib only; identical in workload.py and expected.py) ----
import random

WORDS = ["Hauptbeschäftigung", "Größe", "Straße", "Bürgerämter", "Prüfungsübersicht", "Lösungsansätze"]
CHARSETS = ("utf-8", "gbk", "latin1")  # documented NameObject decode order at the base commit
DELIMS = b"#()<>[]{}/%"
FONT_SEPS = [b"", b" ", b"\n", b"\r\n", b"\t", b"\x0c"]
PROP_SEPS = [b"", b" ", b"\n"]
SPECIAL_ALPHABET = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.!*+,;:=?@~"
                    "#()<>[]{}/% \t\r\n\x00\x7f" "äöüßéçñ€中文😀")
BROKEN_ALPHABET = b"ABCDEFGHIJ0123456789 ()"


def misencode(word, depth):
    s = word
    for _ in range(depth):
        s = s.encode("utf-8").decode("latin-1")
    return s


def pdf_name(s):
    """Raw PDF name token (with leading '/') for text s: UTF-8 bytes, escape outside ! .. ~ and delimiters (upper hex)."""
    out = ["/"]
    for b in s.encode("utf-8"):
        c = chr(b)
        if b < 0x21 or b > 0x7E or c in "#()<>[]{}/%":
            out.append("#%02X" % b)
        else:
            out.append(c)
    return "".join(out)


def escape_bytes(raw, rng, plain_escape_p):
    """Raw PDF name token for name bytes `raw`: mandatory escapes, plus random escapes of plain bytes, mixed hex case."""
    out = bytearray(b"/")
    for b in raw:
        must = b < 0x21 or b > 0x7E or b in DELIMS
        if must or rng.random() < plain_escape_p:
            out += (b"#%02X" if rng.random() < 0.5 else b"#%02x") % b
        else:
            out.append(b)
    return bytes(out)


def decode_name(raw_bytes):
    """Expected decoded NameObject text for unescaped name bytes (leading '/' included)."""
    for enc in CHARSETS:
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            pass
    raise AssertionError("latin1 never fails")


class Doc:
    def __init__(self):
        self.objs = []

    def reserve(self):
        self.objs.append(None)
        return len(self.objs)

    def set(self, num, body):
        self.objs[num - 1] = body if isinstance(body, bytes) else body.encode("latin-1")

    def add(self, body):
        n = self.reserve()
        self.set(n, body)
        return n

    def stream(self, data, extra="", length=True):
        head = b"<< /Length %d %s>>" % (len(data), extra.encode()) if length else b"<< %s>>" % extra.encode()
        return self.add(head + b"\nstream\n" + data + b"\nendstream")

    def build(self, root):
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, body in enumerate(self.objs):
            offs.append(len(out))
            out += b"%d 0 obj\n" % (i + 1) + body + b"\nendobj\n"
        xref_at = len(out)
        out += b"xref\n0 %d\n" % (len(self.objs) + 1)
        out += b"0000000000 65535 f\r\n"
        for o in offs:
            out += b"%010d 00000 n\r\n" % o
        out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(self.objs) + 1, root, xref_at)
        return bytes(out)


RESAVE_CONTENT = b"/OC /MC0 BDC BT /F1 10 Tf 72 700 Td (Formular Seite) Tj ET EMC"
RESAVE_OPS = [("BDC", ["/OC", "/MC0"]), ("BT", []), ("Tf", ["/F1"]), ("Td", []), ("Tj", []), ("ET", []), ("EMC", [])]


def _page(d, pages_n, token, content, font_tpl=0, font_sep=b" ", prop_sep=b" ", length=True):
    if font_tpl == 0:
        font = d.add(b"<< /Type /Font /Subtype /Type1 /BaseFont " + token + font_sep + b"/Encoding /WinAnsiEncoding >>")
    else:  # name is the last value: followed directly by '>>'
        font = d.add(b"<< /Type /Font /Subtype /Type1 /Encoding /WinAnsiEncoding /BaseFont " + token + b">>")
    c = d.stream(content, length=length)
    return d.add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> "
                 b"/Properties << " % (pages_n, c, font) + token + prop_sep
                 + b"<< /Type /OCG /Name (layer) >> /MC0 << /Type /OCG /Name (base) >> >> >> >>")


def _finish(d, cat, pages_n, kids):
    d.set(pages_n, "<< /Type /Pages /Count %d /Kids [%s] >>" % (len(kids), " ".join("%d 0 R" % k for k in kids)))
    d.set(cat, "<< /Type /Catalog /Pages %d 0 R >>" % pages_n)
    return d.build(cat)


def _make_forms(depth, seed, tagged):
    """resave: byte-identical to the screen fixture wl_3679.make(depth, seed); tagged adds the name as a BDC tag."""
    rng = random.Random(seed)
    d = Doc(); cat = d.reserve(); pages_n = d.reserve()
    kids, facts = [], []
    for p in range(3):
        word = WORDS[rng.randrange(len(WORDS))]
        text = misencode(word, depth - (p % 2))
        tok = pdf_name(text).encode("latin-1")
        if tagged:
            content = b"/OC " + tok + b" BDC BT /F1 10 Tf 72 700 Td (Formular Seite) Tj ET EMC\n/OC /MC0 BDC EMC"
            ops = [("BDC", ["/OC", "/" + text]), ("BT", []), ("Tf", ["/F1"]), ("Td", []), ("Tj", []), ("ET", []),
                   ("EMC", []), ("BDC", ["/OC", "/MC0"]), ("EMC", [])]
        else:
            content, ops = RESAVE_CONTENT, RESAVE_OPS
        kids.append(_page(d, pages_n, tok, content))
        facts.append({"name": "/" + text, "content": content, "ops": ops})
    return _finish(d, cat, pages_n, kids), facts


def _make_special(pages, size, seed):
    rng = random.Random(seed)
    d = Doc(); cat = d.reserve(); pages_n = d.reserve()
    kids, facts = [], []
    for p in range(pages):
        if p % 4 == 3:  # raw high bytes: not always valid UTF-8 (decoder falls back per CHARSETS)
            raw = bytes(rng.choice(b"abcXYZ09_" + bytes(range(0x80, 0x100))) for _ in range(size))
        else:
            raw = "".join(rng.choice(SPECIAL_ALPHABET) for _ in range(size)).encode("utf-8")
        if raw == b"MC0":
            raw = b"MC1"
        tok = escape_bytes(raw, rng, 0.25)
        content = b"BT /F1 9 Tf 40 %d Td (p%d) Tj ET" % (700 - p, p)
        kids.append(_page(d, pages_n, tok, content, font_tpl=p % 2, font_sep=FONT_SEPS[p % len(FONT_SEPS)],
                          prop_sep=PROP_SEPS[p % len(PROP_SEPS)]))
        facts.append({"name": decode_name(b"/" + raw), "content": content, "ops": None})
    return _finish(d, cat, pages_n, kids), facts


def _make_boundary(length, pages, seed):
    """Name tokens whose raw length after '/' is length-1, length, length+1 (cycling): delimiter on chunk edges."""
    rng = random.Random(seed)
    d = Doc(); cat = d.reserve(); pages_n = d.reserve()
    kids, facts = [], []
    for p in range(pages):
        want = max(1, length + (p % 3) - 1)
        raw_tok, text = bytearray(), []
        while len(raw_tok) < want:
            ch = rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
            if want - len(raw_tok) >= 3 and rng.random() < 0.6:
                raw_tok += (b"#%02X" if rng.random() < 0.5 else b"#%02x") % ord(ch)
            else:
                raw_tok += ch.encode()
            text.append(ch)
        tok = b"/" + bytes(raw_tok)
        content = b"BT /F1 9 Tf 40 700 Td (b%d) Tj ET" % p
        kids.append(_page(d, pages_n, tok, content, font_tpl=(p // 3) % 2, font_sep=FONT_SEPS[p % len(FONT_SEPS)],
                          prop_sep=PROP_SEPS[(p // 2) % len(PROP_SEPS)]))
        facts.append({"name": "/" + "".join(text), "content": content, "ops": None})
    return _finish(d, cat, pages_n, kids), facts


def _make_brokenlen(start, pages, seed):
    """Content streams without /Length (damaged file): the reader scans for 'endstream'; data lengths start+p."""
    rng = random.Random(seed)
    d = Doc(); cat = d.reserve(); pages_n = d.reserve()
    kids, facts = [], []
    for p in range(pages):
        n = start + p
        data = bytes(rng.choice(BROKEN_ALPHABET) for _ in range(n))
        text = "Seite%d" % p
        kids.append(_page(d, pages_n, pdf_name(text).encode(), data, length=False))
        facts.append({"name": "/" + text, "content": data + b"\n", "ops": None})
    return _finish(d, cat, pages_n, kids), facts


def build_fixture(case, size, seed):
    """Return (list of (pdf_bytes, page facts), mode). Page facts hold what a correct reader/writer must report."""
    mode, _, arg = case.partition(":")
    arg = int(arg)
    if mode in ("resave", "tagged"):
        if not 1 <= arg <= 8 or not 0 <= size <= 14:
            raise ValueError("docs 1..8, depth 0..14")
        return [_make_forms(size, seed * 1000 + i, mode == "tagged") for i in range(arg)], mode
    if mode == "special":
        return [_make_special(arg, size, seed)], mode
    if mode == "boundary":
        return [_make_boundary(arg, size, seed)], mode
    if mode == "brokenlen":
        return [_make_brokenlen(arg, size, seed)], mode
    raise ValueError("unknown case mode " + mode)


def renumber(name):
    """Expected written token for a decoded name (PDF 32000-1 7.3.5 escaping as pypdf writes it: upper hex)."""
    out = bytearray(b"/")
    for c in name[1:]:
        if c > "~":
            for x in c.encode("utf-8"):
                out += b"#%02X" % x
        elif ord(c) <= 32 or c in "#()<>[]{}/%":
            out += b"#%02X" % ord(c)
        else:
            out += c.encode("ascii")
    return bytes(out)
# ---- end fixture generator ----

_WS = rb"[ \t\r\n\x0c]*"
_TOKEN = rb"(/[^ \t\r\n\x0c\x00()<>\[\]{}/%]*)"
_BASEFONT = re.compile(rb"/BaseFont" + _WS + _TOKEN)
_PROPERTIES = re.compile(rb"/Properties" + _WS + rb"<<" + _WS + _TOKEN)


def _ops(page, reader):
    from pypdf.generic import ContentStream, NameObject
    stream = ContentStream(page["/Contents"].get_object(), reader)
    return [(op.decode("latin-1"), [str(x) for x in operands if isinstance(x, NameObject)])
            for operands, op in stream.operations]


def run(case, size, seed):
    from pypdf import PdfReader, PdfWriter

    docs, mode = build_fixture(case, size, seed)
    names, written = [], []
    contents, ops_digest = hashlib.sha256(), hashlib.sha256()
    names_ok, pages, ops_pages = True, 0, 0
    for data, _facts in docs:
        reader = PdfReader(io.BytesIO(data))
        writer = PdfWriter()
        for page in reader.pages:
            if mode == "tagged":
                ops_digest.update(json.dumps(_ops(page, reader), ensure_ascii=True).encode() + b"\n")
                ops_pages += 1
            writer.add_page(page)
        buffer = io.BytesIO()
        writer.write(buffer)
        out = buffer.getvalue()
        written.extend(m.group(1) for m in _BASEFONT.finditer(out))
        written.extend(m.group(1) for m in _PROPERTIES.finditer(out))
        again = PdfReader(io.BytesIO(out))
        for page in again.pages:
            pages += 1
            keys = [k for k in page["/Resources"]["/Properties"] if k != "/MC0"]
            base_font = page["/Resources"]["/Font"]["/F1"].get_object()["/BaseFont"]
            names_ok = names_ok and len(keys) == 1 and keys[0] == base_font
            names.append(str(base_font))
            body = page.get_contents().get_data()
            contents.update(b"%d:" % len(body) + body)
    written.sort()
    joined = "\n".join(names).encode("utf-8", "surrogatepass")
    result = {
        "pages": pages, "names_ok": names_ok,
        "names_sha256": hashlib.sha256(joined).hexdigest(), "names_chars": sum(len(n) for n in names),
        "written_count": len(written), "written_sha256": hashlib.sha256(b"\n".join(written)).hexdigest(),
        "contents_sha256": contents.hexdigest(),
        "ops_pages": ops_pages, "ops_sha256": ops_digest.hexdigest() if ops_pages else None,
    }
    if len(joined) <= 600:
        result["names"] = names
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
