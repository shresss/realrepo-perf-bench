"""Deterministic generator for PDFs whose non-stream objects live in ONE object stream
(the layout DocuSign / PDFKit.NET style producers emit), with an xref stream.
"""
import zlib


def _ser_xref_entry(t, a, b):
    return bytes([t]) + a.to_bytes(4, "big") + b.to_bytes(2, "big")


def build_pdf(n_pages, fields_per_page, *, title="Invoice", unicode_names=False,
              broken_index=None, incremental_override=None):
    objs = {}      # num -> bytes, packed into the object stream
    streams = {}   # num -> bytes (content streams, stored as regular objects)
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[3] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
               b"/Encoding /WinAnsiEncoding >>")
    nxt = 4
    kids = []
    for p in range(n_pages):
        page, contents = nxt, nxt + 1
        nxt += 2
        annots = []
        for f in range(fields_per_page):
            w, mk = nxt, nxt + 1
            nxt += 2
            x = 40 + (f % 6) * 90
            y = 700 - (f // 6) * 14 % 650
            if unicode_names:
                name = ("﻿" + f"Feld äöü 日本 {p}-{f}").encode("utf-16-be")
                tname = b"<" + name.hex().encode() + b">"
            else:
                tname = b"(field_%d_%d)" % (p, f)
            objs[w] = (b"<< /Type /Annot /Subtype /Widget /FT /Tx /T " + tname +
                       b" /Rect [%d %d %d %d] /F 4 /DA (/Helv 9 Tf 0 g) /MK %d 0 R"
                       b" /P %d 0 R /V (amount %d.%02d) /Ff %d >>"
                       % (x, y, x + 85, y + 12, mk, page, (p * 37 + f) % 9999, f % 100,
                          (f % 3) << 12))
            objs[mk] = b"<< /BC [0 0 0] /BG [1 1 %d] /R %d >>" % (f % 2, (f % 4) * 90)
            annots.append(w)
        objs[page] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                      b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R "
                      b"/Annots [%s] >>" % (contents, b" ".join(b"%d 0 R" % a for a in annots)))
        streams[contents] = (b"BT /F1 12 Tf 72 740 Td (" + title.encode("latin-1") +
                             b" page %d of %d) Tj ET" % (p + 1, n_pages))
        kids.append(page)
    objs[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))

    stm_num = nxt
    xref_num = nxt + 1
    size = nxt + 2
    order = sorted(objs)
    body = b""
    header_parts = []
    for i, num in enumerate(order):
        off = len(body)
        idx_num = num
        if broken_index is not None and i == broken_index:
            idx_num = num  # keep number; corrupt the body below instead
        header_parts.append(b"%d %d" % (idx_num, off))
        data = objs[num]
        if broken_index is not None and i == broken_index:
            data = b"<< /Broken [ 1 2 "  # unterminated
        body += data + b"\n"
    header = b" ".join(header_parts) + b"\n"
    raw = header + body
    comp = zlib.compress(raw, 6)

    out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(streams):
        offsets[num] = len(out)
        d = streams[num]
        out += b"%d 0 obj\n<< /Length %d >>\nstream\n" % (num, len(d)) + d + b"\nendstream\nendobj\n"
    offsets[stm_num] = len(out)
    out += (b"%d 0 obj\n<< /Type /ObjStm /N %d /First %d /Length %d /Filter /FlateDecode >>\n"
            b"stream\n" % (stm_num, len(order), len(header), len(comp)) + comp +
            b"\nendstream\nendobj\n")
    offsets[xref_num] = len(out)
    entries = bytearray()
    positions = {num: i for i, num in enumerate(order)}
    for num in range(size):
        if num == 0:
            entries += _ser_xref_entry(0, 0, 65535)
        elif num in offsets:
            entries += _ser_xref_entry(1, offsets[num], 0)
        elif num in objs:
            entries += _ser_xref_entry(2, stm_num, positions[num])
        else:
            entries += _ser_xref_entry(0, 0, 0)
    out += (b"%d 0 obj\n<< /Type /XRef /Size %d /W [1 4 2] /Root 1 0 R /Length %d >>\n"
            b"stream\n" % (xref_num, size, len(entries)) + bytes(entries) +
            b"\nendstream\nendobj\n")
    out += b"startxref\n%d\n%%%%EOF\n" % offsets[xref_num]

    if incremental_override is not None:
        # incremental update: override one object that lives in the ObjStm
        onum, newbody = incremental_override
        prev = offsets[xref_num]
        new_off = len(out)
        out += b"%d 0 obj\n" % onum + newbody + b"\nendobj\n"
        x2 = len(out)
        e2 = _ser_xref_entry(1, new_off, 0) + _ser_xref_entry(1, x2, 0)
        out += (b"%d 0 obj\n<< /Type /XRef /Size %d /W [1 4 2] /Index [%d 1 %d 1] /Root 1 0 R "
                b"/Prev %d /Length %d >>\nstream\n" % (size, size + 1, onum, size, prev, len(e2))
                + e2 + b"\nendstream\nendobj\n")
        out += b"startxref\n%d\n%%%%EOF\n" % x2
    return bytes(out)

import argparse
import hashlib
import io
import json


def run(case, size, seed):
    from pypdf import PdfReader, PdfWriter
    n_pages = 4 if case == "forms" or case == "floor" else 2
    title = "Invoice %d" % seed
    override = None
    if case == "override":
        override = (6, b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (OVERRIDDEN) /Rect [0 0 1 1] /V (updated) /Ff 0 /MK << /BG [0 1 0] /R 0 >> >>")
    data = build_pdf(n_pages, size, title=title, unicode_names=case == "unicode", incremental_override=override)
    before = hashlib.sha256(data).hexdigest()
    if case == "floor":
        return {"floor": True, "bytes": len(data)}
    reader = PdfReader(io.BytesIO(data), strict=case == "strict")
    writer = PdfWriter()
    order = list(range(n_pages))
    if case == "reverse":
        order.reverse()
    for i in order:
        writer.add_page(reader.pages[i])
    output = io.BytesIO()
    writer.write(output)
    reread = PdfReader(io.BytesIO(output.getvalue()))
    pages = []
    for page in reread.pages:
        widgets = []
        for ref in page["/Annots"]:
            widget = ref.get_object()
            mk = widget["/MK"]
            widgets.append({"name":str(widget["/T"]), "value":str(widget["/V"]), "rect":[int(v) for v in widget["/Rect"]], "flags":int(widget["/Ff"]), "background":[int(v) for v in mk["/BG"]], "rotation":int(mk["/R"])})
        pages.append({"box":[int(v) for v in page.mediabox], "contents":page.get_contents().get_data().decode('latin-1'), "widgets":widgets})
    digest=hashlib.sha256(json.dumps(pages,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return {"pages":len(pages),"widgets":sum(len(p['widgets']) for p in pages),"digest":digest,"input_unchanged":hashlib.sha256(reader.stream.getvalue()).hexdigest() == before,"sample":pages if size <= 3 else None}


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--size',required=True,type=int);p.add_argument('--seed',required=True,type=int)
    a=p.parse_args();print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True,allow_nan=False))
