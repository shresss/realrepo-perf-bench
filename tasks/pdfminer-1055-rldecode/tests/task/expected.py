"""Independent oracle for pdfminer-1055-rldecode. Standard library only; never imports pdfminer.

Recomputes from the generator what a behavior-preserving pdfminer reports: the extracted text (one
"Delivery receipt N scanned copy" line plus a form feed per page) and, for each page, the exact bytes of
the BMP file pdfminer's ImageWriter writes from the decoded image: BITMAPFILEHEADER + BITMAPINFOHEADER,
a grey palette (256 entries for 8-bit, 2 for 1-bit, none for 24-bit), bottom-up rows each padded to a
multiple of 4 bytes, except that the padding after the last row in the file (the top image row) is never
written. File names: Im1.bmp for page 1, Im1.<k-2>.bmp for page k >= 2. Decoded image = the generator's
raw pixel bytes (the RunLength stream ends at the EOD byte 128, or at the end of the stream without one).
"""
import hashlib
import struct


# ---- fixture generator (stdlib only; identical in workload.py and expected.py) ----
# case = "<profile>:<variant>", size = pages (one RunLengthDecode image per page).
PROFILES = {
    # name: (width px, height px, bits per component, colour space, kind)
    "gray8": (600, 800, 8, "DeviceGray", "scan"),       # 75 dpi letter fax-quality scan (declared 02:35)
    "gray8odd": (601, 37, 8, "DeviceGray", "scan"),     # odd width: BMP row padding
    "rgb": (50, 30, 8, "DeviceRGB", "scan"),            # 24-bit BMP path, /Filter given as an array
    "drawing": (5400, 3600, 1, "DeviceGray", "drawing"),  # ARCH D sheet at 150 dpi, 1-bit line art
    "drawmini": (203, 60, 1, "DeviceGray", "drawing"),  # width not a multiple of 8 or 32
}
VARIANTS = ("eod", "noeod", "junk", "maxruns")
MAXRUNS_CYCLE = (("lit", 128), ("rep", 128), ("rep", 2), ("lit", 1), ("rep", 129), ("lit", 3))


def _parse(case):
    profile, variant = case.split(":")
    if profile not in PROFILES or variant not in VARIANTS:
        raise ValueError("unknown case " + case)
    if variant == "maxruns" and PROFILES[profile][4] != "scan":
        raise ValueError("maxruns needs a scan profile")
    return profile, variant


def rle_row(row_segments):
    out = bytearray()
    for kind, payload in row_segments:
        if kind == "rep":
            val, n = payload
            while n > 0:
                k = min(n, 128)
                if k == 1:
                    out += bytes((0, val))
                else:
                    out += bytes((257 - k, val))
                n -= k
        else:
            lit = payload
            for s in range(0, len(lit), 128):
                chunk = lit[s:s + 128]
                out.append(len(chunk) - 1)
                out += chunk
    return out


def _segments(row):
    """Split a row into maximal repeat runs (length >= 2) and literal stretches."""
    segs, lit, i, n = [], bytearray(), 0, len(row)
    while i < n:
        j = i + 1
        while j < n and row[j] == row[i]:
            j += 1
        if j - i >= 2:
            if lit:
                segs.append(("lit", bytes(lit)))
                lit = bytearray()
            segs.append(("rep", (row[i], j - i)))
        else:
            lit.append(row[i])
        i = j
    if lit:
        segs.append(("lit", bytes(lit)))
    return segs


def _scan_image(rng, row_bytes, H, text_rows, row_h, ink, margin, maxruns):
    """Scanned page: white rows as 128-byte repeat runs, text rows with literal ink spans."""
    enc = bytearray()
    raw = bytearray()
    starts = sorted(rng.sample(range(margin, H - margin - row_h, row_h + 4), text_rows))
    text_lines = set()
    for s in starts:
        text_lines.update(range(s, s + row_h))
    for y in range(H):
        if y in text_lines and maxruns:
            segs, left, k = [], row_bytes, 0
            while left > 0:
                kind, n = MAXRUNS_CYCLE[k % len(MAXRUNS_CYCLE)]
                n = min(n, left)
                segs.append(("lit", rng.randbytes(n)) if kind == "lit" else ("rep", (rng.randrange(256), n)))
                left -= n
                k += 1
        elif y in text_lines:
            total = int(row_bytes * ink)
            nspans = 5
            span = total // nspans
            gap_total = row_bytes - span * nspans
            cuts = sorted(rng.sample(range(1, gap_total), nspans))
            gaps = [cuts[0]] + [cuts[i] - cuts[i - 1] for i in range(1, nspans)] + [gap_total - cuts[-1]]
            segs = []
            for i in range(nspans):
                segs.append(("rep", (255, gaps[i])))
                segs.append(("lit", rng.randbytes(span)))
            segs.append(("rep", (255, gaps[-1])))
            segs = [sg for sg in segs if not (sg[0] == "rep" and sg[1][1] == 0)]
        else:
            segs = [("rep", (255, row_bytes))]
        enc += rle_row(segs)
        for k, p in segs:
            raw += (bytes((p[0],)) * p[1]) if k == "rep" else p
    assert len(raw) == row_bytes * H
    return enc, bytes(raw)


def _drawing_image(rng, W, H, row_bytes):
    """1-bit line art (white = 1 bits): long white runs crossed by thin vertical lines,
    occasional full-width rules, and a title block of dense literal bytes."""
    enc = bytearray()
    raw = bytearray()
    bands = []
    for b in range(3):
        row = bytearray(b"\xff" * row_bytes)
        for x in rng.sample(range(8, W - 8), max(2, W // 135)):
            for px in (x, x + 1):
                row[px // 8] &= ~(0x80 >> (px % 8)) & 0xFF
        row = bytes(row)
        bands.append((row, bytes(rle_row(_segments(row)))))
    rules = set()
    for y in rng.sample(range(4, H - 4), max(2, H // 150)):
        rules.update((y, y + 1, y + 2))
    tb_top, tb_left = H - H // 8, row_bytes - row_bytes // 4
    black = bytes(row_bytes)
    black_enc = bytes(rle_row([("rep", (0, row_bytes))]))
    for y in range(H):
        row, row_enc = bands[min(2, 3 * y // H)]
        if y in rules:
            row, row_enc = black, black_enc
        elif y >= tb_top and y % 3 != 0:
            row = row[:tb_left] + rng.randbytes(row_bytes - tb_left)
            row_enc = bytes(rle_row(_segments(row)))
        enc += row_enc
        raw += row
    assert len(raw) == row_bytes * H
    return enc, bytes(raw)


def make_pdf(case, pages, seed):
    """Return (pdf_bytes, facts). facts: per page (row_bytes, bits_for_bmp, width, height, raw)."""
    import random
    profile, variant = _parse(case)
    if pages < 1:
        raise ValueError("at least one page")
    W, H, bits, cs, kind = PROFILES[profile]
    comps = 3 if cs == "DeviceRGB" else 1
    row_bytes = (W * bits * comps + 7) // 8
    rng = random.Random(seed)
    objs = []
    facts = []

    def add(b):
        objs.append(b)
        return len(objs)

    catalog = add(None)
    pages_id = add(None)
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids = []
    for p in range(pages):
        if kind == "scan" and profile == "gray8":
            enc, raw = _scan_image(rng, row_bytes, H, 20, 10, 0.25, 40, variant == "maxruns")
        elif kind == "scan":
            enc, raw = _scan_image(rng, row_bytes, H, 2, 4 if H < 36 else 5, 0.25, 3 if H < 36 else 4,
                                   variant == "maxruns")
        else:
            enc, raw = _drawing_image(rng, W, H, row_bytes)
        if variant != "noeod":
            enc.append(128)
        if variant == "junk":
            enc += bytes((5,)) + b"JUNK!!" + bytes((250, 0x41)) + rng.randbytes(9)
        facts.append((row_bytes, bits * comps, W, H, raw))
        filt = b"[/RunLengthDecode]" if cs == "DeviceRGB" else b"/RunLengthDecode"
        img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent %d "
                  b"/Filter %s /Length %d >>\nstream\n" % (W, H, cs.encode(), bits, filt, len(enc))
                  + bytes(enc) + b"\nendstream")
        content = (b"BT /F1 12 Tf 72 760 Td (Delivery receipt %d scanned copy) Tj ET q 540 0 0 720 36 20 cm /Im1 Do Q"
                   % (p + 1))
        cs_id = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page = add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 %d 0 R >> "
                   b"/XObject << /Im1 %d 0 R >> >> /Contents %d 0 R >>" % (pages_id, font, img, cs_id))
        kids.append(page)
    objs[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    objs[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, x)
    return bytes(out), facts
# ---- end fixture generator ----


SMALL_DECODED_BYTES = 1000000


def _bmp(row_bytes, bits, width, height, raw):
    ncols = {1: 2, 8: 256, 24: 0}[bits]
    linesize = (((width * bits + 7) // 8) + 3) // 4 * 4
    datasize = linesize * height
    headersize = 14 + 40 + ncols * 4
    out = bytearray(struct.pack("<ccIHHI", b"B", b"M", headersize + datasize, 0, 0, headersize))
    out += struct.pack("<IiiHHIIIIII", 40, width, height, 1, bits, 0, datasize, 0, 0, ncols, 0)
    if ncols == 2:
        out += bytes((0, 0, 0, 0, 255, 255, 255, 0))
    elif ncols == 256:
        for i in range(256):
            out += bytes((i, i, i, 0))
    body = bytearray(datasize)
    for y in range(height):
        pos = datasize - (y + 1) * linesize
        body[pos:pos + row_bytes] = raw[y * row_bytes:(y + 1) * row_bytes]
    end = datasize - linesize + row_bytes  # top row is last in the file; its padding is never written
    return bytes(out + body[:end])


def expected(case, size, seed):
    _, facts = make_pdf(case, size, seed)
    text = "".join("Delivery receipt %d scanned copy\f" % (p + 1) for p in range(len(facts)))
    images = []
    for p, (row_bytes, bits, width, height, raw) in enumerate(facts):
        name = "Im1.bmp" if p == 0 else "Im1.%d.bmp" % (p - 1)
        data = _bmp(row_bytes, bits, width, height, raw)
        images.append([name, len(data), hashlib.sha256(data).hexdigest()])
    images.sort()
    result = {"pages": len(facts), "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
              "text_head": text[:80], "images": images}
    if sum(len(f[4]) for f in facts) <= SMALL_DECODED_BYTES:
        result["decoded"] = [[len(f[4]), hashlib.sha256(f[4]).hexdigest()] for f in facts]
    return result
