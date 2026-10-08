"""Independent stdlib-only oracle for the fsspec-2091 reference-read workload.

Never imports fsspec or workload.py. It rebuilds the same deterministic reference set, computes the
bytes every key must return straight from the generated file contents, and computes the fetch plan
(the coalesced byte ranges requested from the remote store) from the documented coalescing rules of
the untouched checkout:

  * inline references never touch the store; references to a file that is also referenced whole are
    served from the single whole-file read of that file;
  * the remaining ranges are grouped per file and sorted; a range contained in another range of the
    same file is not fetched separately;
  * consecutive ranges of a file are merged while the gap to the open block is <= max_gap and the
    merged block would not exceed max_block (end - block start); otherwise a new block starts.

Requested ranges are normalized like the workload's store: missing start -> 0, missing end -> file
length. Valid only under the disclosed precondition (each key requested once; no two range references
to the same file share a start offset), which every case here satisfies.
"""
import base64
import hashlib

DEFAULT_MAX_GAP = 64_000
DEFAULT_MAX_BLOCK = 256_000_000
RAW_LIMIT = 64


def _payload(fid, length):
    pattern = bytes((i * 7 + fid) % 251 for i in range(251))
    return (pattern * (length // 251 + 1))[:length]


def _fixture(case, size, seed):
    if type(size) is not int or size < 0 or size > 50_000:
        raise ValueError("size must be an integer in 0..50000")
    if type(seed) is not int or not 0 <= seed < 1_000_000:
        raise ValueError("seed must be an integer in 0..999999")
    files, refs, options, on_error = {}, {}, {}, "raise"
    if case == "variable":
        per = size // 6
        for f in range(6):
            url = "objstore://archive/tas_2025%02d.nc" % (f + 1)
            off = 4096
            for c in range(per):
                n = 2000 + (c * 37 + f * 101 + seed * 53) % 4001
                refs["tas/%d.%d" % (f, c)] = [url, off, n]
                off += n + 64 + (c * 13 + f + seed) % 512
            files[url] = (f, off)
        keys = sorted(refs, key=lambda k: (((int(k.split(".")[1]) * 7919 + seed) % 6007), k))
    elif case == "single_file":
        url = "objstore://archive/pr_2025.h5"
        off = 8192
        for c in range(size):
            n = 1500 + (c * 53 + seed * 7) % 5001
            refs["pr/0.%d" % c] = [url, off, n]
            off += n + 32 + (c * 29 + seed) % 900
        files[url] = (9, off)
        options = {"max_block": 1_048_576}
        keys = sorted(refs, key=lambda k: (((int(k.split(".")[1]) * 4099 + seed) % 8191), k))
    elif case == "overlap":
        for f in range(2):
            url = "objstore://halo/part%d.bin" % f
            start, last_end = 1000, 0
            for c in range(size):
                n = 400 + (c * 11 + seed + f) % 200
                refs["h%d/%d" % (f, c)] = [url, start, n]
                last_end = max(last_end, start + n)
                start += 300 + (c * 7 + seed) % 50
            files[url] = (20 + f, last_end + 500)
        keys = sorted(refs, reverse=True)
    elif case == "nested":
        for f in range(2):
            url = "objstore://nested/file%d.nc" % f
            off = 512
            for c in range(size):
                n = 600 + (c * 17 + seed + f) % 300
                refs["n%d/chunk%d" % (f, c)] = [url, off, n]
                refs["n%d/hdr%d" % (f, c)] = [url, off + 1 + (c + seed) % 5, 16 + (c * 3 + seed) % 40]
                off += n + 100 + (c * 5 + seed) % 200
            files[url] = (30 + f, off)
        keys = sorted(refs)
    elif case == "chain_block":
        a, b = "objstore://chain/a.bin", "objstore://chain/b.bin"
        for c in range(size):
            refs["a/%d" % c] = [a, c * 90 + seed % 7, 120]
        files[a] = (40, size * 90 + 400)
        for c in range(size):
            refs["b/%d" % c] = [b, c * 300, 100 + (c + seed) % 50]
        files[b] = (41, size * 300 + 400)
        options = {"max_gap": 0, "max_block": 600}
        keys = sorted(refs)
    elif case == "gaps":
        url = "objstore://gaps/g.bin"
        off = 0
        for c in range(size):
            n = 80 + (c * 13 + seed) % 40
            refs["g/%d" % c] = [url, off, n]
            off += n + (0, 50, 150, 100, 101)[(c + seed) % 5]
        files[url] = (50, off + 10)
        options = {"max_gap": 100}
        keys = sorted(refs)
    elif case == "whole":
        a, b, c3 = "objstore://w/a.bin", "objstore://w/b.bin", "objstore://w/c.bin"
        files[a], files[b], files[c3] = (60, 3000 + seed % 100), (61, 5000), (62, 1234)
        refs["a/all"] = [a]
        for c in range(size):
            refs["a/%d" % c] = [a, 10 + c * 97, 50]
            refs["b/%d" % c] = [b, 7 + c * 113 + seed % 11, 60]
        refs["c/all"] = [c3]
        keys = sorted(refs)
    elif case == "inline":
        url = "objstore://inline/x.bin"
        for c in range(size):
            refs["x/%d" % c] = [url, 33 + c * 200, 150 + (c + seed) % 30]
            if c % 3 == 0:
                refs["x/raw%d" % c] = "raw-%d-%d" % (c, seed)
            if c % 4 == 1:
                text = ("inline payload %d %d" % (c, seed)).encode()
                refs["x/b64_%d" % c] = "base64:" + base64.b64encode(text).decode()
        files[url] = (70, 33 + size * 200 + 300)
        keys = sorted(refs, reverse=True)
    elif case == "zero_len":
        url = "objstore://z/z.bin"
        off = 64
        for c in range(size):
            n = 300 + (c * 19 + seed) % 100
            refs["z/%d" % c] = [url, off, n]
            refs["z/empty%d" % c] = [url, off + n + 3, 0]
            off += n + 20
        files[url] = (80, off + 64)
        keys = sorted(refs)
    elif case == "missing":
        url = "objstore://m/m.bin"
        for c in range(size):
            refs["m/%d" % c] = [url, c * 500 + seed % 13, 200]
        files[url] = (90, size * 500 + 300)
        keys = sorted(refs) + ["m/not-there", "zzz/also-missing"]
        on_error = "return"
    elif case == "single_key":
        m = max(size, 1)
        url = "objstore://s/s.bin"
        for c in range(m):
            refs["s/%d" % c] = [url, 17 + c * 100, 70]
        files[url] = (95, 17 + m * 100 + 100)
        keys = "s/%d" % (seed % m)
    elif case == "empty":
        url = "objstore://e/e.bin"
        for c in range(size):
            refs["e/%d" % c] = [url, c * 100, 50]
        files[url] = (99, size * 100 + 100)
        keys = []
    else:
        raise ValueError("unsupported case %r" % (case,))
    return files, refs, keys, options, on_error


def _value(ref, data):
    if isinstance(ref, str):
        raw = ref.encode()
        return base64.b64decode(raw[7:]) if raw.startswith(b"base64:") else raw
    blob = data[ref[0]]
    if len(ref) == 1:
        return blob
    return blob[ref[1]:ref[1] + ref[2]]


def _plan(refs, keys, files, max_gap, max_block):
    entries = []
    for key in keys:
        ref = refs.get(key)
        if ref is None or isinstance(ref, str):
            continue
        entries.append((ref[0], None, None) if len(ref) == 1 else (ref[0], ref[1], ref[1] + ref[2]))
    whole = {u for u, s, _ in entries if s is None}
    todo = [e for e in entries if e[1] is None] + [e for e in entries if e[1] is not None and e[0] not in whole]
    by_file = {}
    for url, start, end in todo:
        by_file.setdefault(url, []).append((start, end))
    blocks = []
    for url in sorted(by_file):
        spans = by_file[url]
        if any(s is None for s, _ in spans):
            blocks.append((url, 0, files[url][1]))
            continue
        # drop ranges contained in another range of the same file (all-pairs semantics)
        spans.sort(key=lambda se: (se[0], -se[1]))
        kept, reach = [], None
        for i, (s, e) in enumerate(spans):
            dup = (i > 0 and spans[i - 1] == (s, e)) or (i + 1 < len(spans) and spans[i + 1] == (s, e))
            if dup or (reach is not None and reach >= e):
                pass
            else:
                kept.append((s, e))
            reach = e if reach is None else max(reach, e)
        kept.sort()
        cur_s, cur_e = kept[0]
        for s, e in kept[1:]:
            if s - cur_e > max_gap or (max_block is not None and e - cur_s > max_block):
                blocks.append((url, cur_s, cur_e))
                cur_s, cur_e = s, e
            else:
                cur_e = e
        blocks.append((url, cur_s, cur_e))
    return sorted((u.split("://", 1)[1], s, e) for u, s, e in blocks)


def _token(value):
    return value if isinstance(value, bytes) else ("EXC:" + value).encode()


def expected(case, size, seed):
    files, refs, keys, options, on_error = _fixture(case, size, seed)
    data = {url: _payload(fid, length) for url, (fid, length) in files.items()}
    max_gap = options.get("max_gap", DEFAULT_MAX_GAP)
    max_block = options.get("max_block", DEFAULT_MAX_BLOCK)
    key_list = [keys] if isinstance(keys, str) else list(keys)
    plan = _plan(refs, key_list, files, max_gap, max_block)
    out = {}
    if isinstance(keys, str):
        value = _value(refs[keys], data)
        out.update(kind="bytes", n=1, digest=hashlib.sha256(value).hexdigest(),
                   raw=value.hex() if len(value) <= 4096 else None)
    else:
        result = {}
        for key in key_list:
            if key in refs:
                result[key] = _value(refs[key], data)
            elif on_error == "return":
                result[key] = "FileNotFoundError"
            elif on_error != "omit":
                return {"kind": "raised:FileNotFoundError"}
        h = hashlib.sha256()
        for key in sorted(result):
            h.update(key.encode())
            h.update(b"\0")
            h.update(_token(result[key]))
            h.update(b"\1")
        out.update(kind="dict", n=len(result), digest=h.hexdigest(),
                   raw=({k: _token(result[k]).hex() for k in sorted(result)} if len(result) <= RAW_LIMIT else None))
    h = hashlib.sha256()
    for path, start, end in plan:
        h.update(("%s|%d|%d\n" % (path, start, end)).encode())
    out["ranges_count"] = len(plan)
    out["ranges_sha256"] = h.hexdigest()
    out["requested_bytes"] = sum(end - start for _, start, end in plan)
    out["ranges"] = [list(r) for r in plan] if len(plan) <= RAW_LIMIT else None
    return out
