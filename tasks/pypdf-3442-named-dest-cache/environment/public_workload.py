"""Copy a hyperlinked manual through pypdf's public API; no expected answers.

Declared before this build's timing: 120 and 300 pages, four named anchors and
three named links plus one direct link per page. A 300-page technical manual
has 1200 anchors and 900 named internal links. Names use 32-entry name-tree
leaves. The 400-page screening case is retained in the upstream screen only.
"""
import argparse
import hashlib
import io
import json
import os
import random


class _Document:
    def __init__(self):
        self.objects = []

    def reserve(self):
        self.objects.append(None)
        return len(self.objects)

    def put(self, number, body):
        self.objects[number - 1] = body.encode("latin-1") if isinstance(body, str) else body

    def add(self, body):
        number = self.reserve()
        self.put(number, body)
        return number

    def build(self, root):
        data = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(self.objects, 1):
            offsets.append(len(data))
            data += b"%d 0 obj\n" % number + body + b"\nendobj\n"
        xref = len(data)
        data += b"xref\n0 %d\n0000000000 65535 f\r\n" % (len(offsets) + 1)
        for offset in offsets:
            data += b"%010d 00000 n\r\n" % offset
        data += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(offsets) + 1, root, xref)
        return bytes(data)


def fixture(pages, seed, layout="tree", reverse=False):
    """An xref-valid PDF built without the package under test."""
    rng = random.Random(seed)
    doc = _Document()
    catalog, page_root, dest_root = doc.reserve(), doc.reserve(), doc.reserve()
    font = doc.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    refs = [doc.reserve() for _ in range(pages)]
    names = [f"sec.{i:05d}" for i in range(4 * pages)]
    for page, ref in enumerate(refs):
        text = f"BT /F1 11 Tf 72 720 Td (Chapter {page // 20} page {page}) Tj ET".encode()
        content = doc.add(b"<< /Length %d >>\nstream\n" % len(text) + text + b"\nendstream")
        annotations = []
        for slot in range(3):
            name = names[rng.randrange(len(names))] if names and layout != "none" else "missing"
            if layout == "legacy":
                name = "/" + name
            route = f"/A << /S /GoTo /D ({name}) >>" if slot == 2 else f"/Dest ({name})"
            annotations.append(doc.add(f"<< /Type /Annot /Subtype /Link /Rect [72 {600-20*slot} 300 {612-20*slot}] /Border [0 0 0] {route} >>"))
        annotations.append(doc.add(f"<< /Type /Annot /Subtype /Link /Rect [72 40 200 52] /Border [0 0 0] /Dest [{refs[0]} 0 R /Fit] >>"))
        doc.put(ref, f"<< /Type /Page /BenchPage {page} /Parent {page_root} 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R /Resources << /Font << /F1 {font} 0 R >> >> /Annots [{' '.join(f'{a} 0 R' for a in annotations)}] >>")
    entries = []
    for ordinal, name in enumerate(names):
        target = pages - 1 - ordinal // 4 if reverse else ordinal // 4
        entries.append(f"({name}) [{refs[target]} 0 R /XYZ 0 {792 - 30*(ordinal % 4)} 0]")
    if layout == "legacy":
        doc.put(dest_root, "<< " + " ".join("/" + entry[1:10] + entry[11:] for entry in entries) + " >>")
        names_catalog = f"/Dests {dest_root} 0 R"
    elif layout == "none":
        doc.put(dest_root, "<< >>")
        names_catalog = ""
    else:
        kids = []
        for offset in range(0, len(entries), 32):
            chunk = entries[offset:offset+32]
            kids.append(doc.add(f"<< /Limits [({names[offset]}) ({names[offset+len(chunk)-1]})] /Names [{' '.join(chunk)}] >>"))
        doc.put(dest_root, "<< /Kids [" + " ".join(f"{kid} 0 R" for kid in kids) + "] >>")
        names_catalog = f"/Names << /Dests {dest_root} 0 R >>"
    doc.put(page_root, f"<< /Type /Pages /Count {pages} /Kids [{' '.join(f'{r} 0 R' for r in refs)}] >>")
    doc.put(catalog, f"<< /Type /Catalog /Pages {page_root} 0 R {names_catalog} >>")
    return doc.build(catalog)


def _number(value):
    return None if value is None else int(value)


def _names(reader):
    page_numbers = {page.indirect_reference: number for number, page in enumerate(reader.pages)}
    return [[str(name), page_numbers.get(dest.page), str(dest.typ),
             _number(dest.left), _number(dest.top), _number(dest.zoom)]
            for name, dest in sorted(reader.named_destinations.items())]


def _output(reader):
    destinations = _names(reader)
    targets = {name: page for name, page, *_ in destinations}
    pages = []
    for page in reader.pages:
        links = []
        for ref in page.get("/Annots", []):
            annotation = ref.get_object()
            route = "action" if "/A" in annotation else "dest"
            destination = annotation["/A"]["/D"] if route == "action" else annotation["/Dest"]
            if isinstance(destination, str):
                links.append([route, str(destination), targets.get(str(destination))])
            else:
                target = destination[0].get_object()
                links.append(["direct", int(target["/BenchPage"]), reader.get_page_number(target), str(destination[1])])
        pages.append([int(page["/BenchPage"]), hashlib.sha256(page.get_contents().get_data()).hexdigest(), links])
    root = reader.root_object.get("/Names", {})
    raw = root.get("/Dests", {}).get("/Names", []) if isinstance(root, dict) else []
    # Dereference dictionaries through public PDF object access rather than `.get`.
    if "/Names" in reader.root_object and "/Dests" in reader.root_object["/Names"]:
        raw = reader.root_object["/Names"]["/Dests"].get("/Names", [])
    return {"pages": pages, "named": destinations, "raw_name_count": len(raw) // 2}


def run(case, size, seed):
    import pypdf
    from pypdf import PdfReader, PdfWriter
    expected_root = os.environ.get("AQ_EXPECT_TREE")
    if expected_root:
        assert os.path.realpath(pypdf.__file__).startswith(os.path.realpath(expected_root) + os.sep), pypdf.__file__
    valid = {"manual", "subset-reverse", "duplicate", "append", "legacy", "no-names", "reader-isolation", "writer-live"}
    if case not in valid or size < 0 or (case in {"duplicate", "writer-live"} and size < 2):
        raise ValueError("invalid workload case or size")
    if case == "writer-live":
        writer = PdfWriter()
        for _ in range(size):
            writer.add_blank_page(612, 792)
        snapshots = [_names(writer)]
        for name, page in [("z", size - 1), ("a", 0), ("m", 1)]:
            writer.add_named_destination(name, page)
            snapshots.append(_names(writer))
        buf = io.BytesIO()
        writer.write(buf)
        payload = {"writer_live": snapshots, "named": _names(PdfReader(io.BytesIO(buf.getvalue())))}
        unchanged = True
    else:
        layout = "legacy" if case == "legacy" else "none" if case == "no-names" else "tree"
        data = fixture(size, seed, layout)
        stream = io.BytesIO(data)
        reader = PdfReader(stream)
        writer = PdfWriter()
        before = _names(reader)
        if case == "reader-isolation":
            other = PdfReader(io.BytesIO(fixture(size, seed + 1, reverse=True)))
            payload = {"readers": [before, _names(other), _names(reader), _names(other)]}
        else:
            selected = list(range(size))
            if case == "subset-reverse":
                selected = list(range(size-1, -1, -2))
            elif case == "duplicate":
                selected = [0, 1, 1, size-1, 0]
            if case == "append":
                writer.append(reader)
            else:
                for page in selected:
                    writer.add_page(reader.pages[page])
            buffer = io.BytesIO()
            writer.write(buffer)
            payload = _output(PdfReader(io.BytesIO(buffer.getvalue())))
            payload["source_named"] = before
            payload["source_named_after"] = _names(reader)
        unchanged = stream.getvalue() == data
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"case": case, "size": size, "seed": seed, "count": len(payload.get("pages", [])),
            "sha256": hashlib.sha256(encoded).hexdigest(), "input_unchanged": unchanged,
            "raw": payload if size <= 12 else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--floor", action="store_true")
    args = parser.parse_args()
    if args.floor:
        import pypdf
        expected_root = os.environ.get("AQ_EXPECT_TREE")
        if expected_root:
            assert os.path.realpath(pypdf.__file__).startswith(os.path.realpath(expected_root) + os.sep)
        answer = {"floor_bytes": len(fixture(args.size, args.seed))}
    else:
        answer = run(args.case, args.size, args.seed)
    print(json.dumps(answer, sort_keys=True, allow_nan=False))
