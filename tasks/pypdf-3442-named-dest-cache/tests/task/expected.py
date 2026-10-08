"""Independent logical-document oracle; stdlib only, no PDF parser or workload import."""
import hashlib
import json
import random


def expected(case, size, seed):
    if case not in {"manual", "subset-reverse", "duplicate", "append", "legacy", "no-names", "reader-isolation", "writer-live"} or size < 0 or (case in {"duplicate", "writer-live"} and size < 2):
        raise ValueError("invalid workload case or size")
    names = [f"sec.{ordinal:05d}" for ordinal in range(4 * size)]
    if case == "legacy":
        names = ["/" + name for name in names]
    source = [[name, ordinal // 4, "/XYZ", 0, 792-30*(ordinal % 4), 0] for ordinal, name in enumerate(names)]
    if case == "no-names":
        source = []
    if case == "reader-isolation":
        reversed_source = [[name, size-1-page, fit, left, top, zoom] for name, page, fit, left, top, zoom in source]
        payload = {"readers": [source, reversed_source, source, reversed_source]}
    elif case == "writer-live":
        snapshots, live = [[]], {}
        for name, page in [("z", size-1), ("a", 0), ("m", 1)]:
            live[name] = [name, page, "/FitH", None, 826, None]
            snapshots.append([live[key] for key in sorted(live)])
        payload = {"writer_live": snapshots, "named": snapshots[-1]}
    else:
        order = list(range(size))
        if case == "subset-reverse":
            order = list(range(size-1, -1, -2))
        elif case == "duplicate":
            order = [0, 1, 1, size-1, 0]
        # Page-copy link resolution uses the last copied occurrence of each source page.
        output_position = {source_page: index for index, source_page in enumerate(order)}
        # Writer page_number uses structural page equality. The first duplicate
        # supplies a new named destination, while direct links retain the final
        # cloned indirect reference. Distinct contents make other pages unequal.
        first_position = {}
        for index, page in enumerate(order):
            first_position.setdefault(page, index)
        rng = random.Random(seed)
        references = []
        for _ in range(size):
            references.append([names[rng.randrange(4*size)] if case != "no-names" else "missing" for _ in range(3)])
        imported = {}
        if case == "append":
            imported = {entry[0]: entry for entry in source}
        else:
            for page in order:
                for name in references[page]:
                    ordinal = int(name.lstrip("/")[4:]) if name != "missing" else None
                    if ordinal is not None and ordinal // 4 in output_position:
                        imported[name] = [name, first_position[ordinal // 4], "/FitH", None, 826, None]
        pages = []
        for page in order:
            links = [["action" if slot == 2 else "dest", name, imported[name][1] if name in imported else None]
                     for slot, name in enumerate(references[page])]
            links.append(["direct", 0, output_position.get(0), "/Fit"])
            content = f"BT /F1 11 Tf 72 720 Td (Chapter {page // 20} page {page}) Tj ET".encode()
            pages.append([page, hashlib.sha256(content).hexdigest(), links])
        payload = {"pages": pages, "named": [imported[key] for key in sorted(imported)],
                   "raw_name_count": len(imported), "source_named": source, "source_named_after": source}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"case": case, "size": size, "seed": seed, "count": len(payload.get("pages", [])),
            "sha256": hashlib.sha256(encoded).hexdigest(), "input_unchanged": True,
            "raw": payload if size <= 12 else None}
