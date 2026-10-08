"""Staging cleanup on fsspec's in-memory filesystem (public API only, no timers).

case "cleanup": a pipeline stage writes a dimension table and two runs of staging outputs into
MemoryFileSystem with fs.pipe, then cleans up: fs.rm(<manifest of the previous run's files>) and
fs.rm("/staging/run-0001", recursive=True). The table and two neighbour prefixes must survive.
case "edges": small rm / write / type-probe scenarios whose results and filesystem snapshots
are compared exactly (error types included).
"""

import argparse
import hashlib
import json

NEIGHBOURS = ("/staging/run-0001-archive/manifest.json", "/staging/run-00010/part-00000.parquet")


def _reset(fs):
    # Same reset as the upstream test fixture `m` (fsspec/conftest.py).
    fs.store.clear()
    fs.pseudo_dirs.clear()
    fs.pseudo_dirs.append("")


def _call(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        return "ok"
    except Exception as exc:  # the exception type is part of the contract
        return type(exc).__name__


def _snap(fs):
    return {"store": sorted(fs.store), "pseudo_dirs": sorted(fs.pseudo_dirs)}


def _store_digest(fs):
    h = hashlib.sha256()
    for key in sorted(fs.store):
        h.update(key.encode() + b"\0" + fs.cat_file(key) + b"\n")
    return h.hexdigest()


def cleanup_data(size, seed):
    shift = seed % 7
    data = {}
    for i in range(size):
        data[f"/warehouse/dim_customer/part-{i:04d}.parquet"] = b"d" * ((i + shift) % 31 + 1)
    stale = [f"/staging/run-0000/table={i % 10:02d}/part-{i:05d}.parquet" for i in range(size)]
    for p in stale:
        data[p] = b"o"
    for s in range(4):
        for i in range(size):
            data[f"/staging/run-0001/shard={s:02d}/part-{i:05d}.parquet"] = b"n" * ((i + s + shift) % 17 + 1)
    for j, p in enumerate(NEIGHBOURS):
        data[p] = b"keep-%d-%d" % (j, seed)
    return data, stale


def _probe(fs, path):
    try:
        kind = fs.info(path)["type"]
    except Exception as exc:
        kind = type(exc).__name__
    return [fs.isfile(path), fs.isdir(path), fs.exists(path), kind]


def run(case, size, seed):
    if type(size) is not int or type(seed) is not int or not 0 <= seed < 10**6:
        raise ValueError("size and seed must be integers")
    import fsspec

    fs = fsspec.filesystem("memory")
    _reset(fs)
    if case == "cleanup":
        if not 1 <= size <= 5000:
            raise ValueError("size must be in 1..5000")
        data, stale = cleanup_data(size, seed)
        fs.pipe(data)
        fs.mkdir("/staging/run-0001/_tmp")
        fs.mkdir("/staging/run-0001/shard=00/_attempt")
        out = {"rm_manifest": _call(fs.rm, stale),
               "rm_run": _call(fs.rm, "/staging/run-0001", recursive=True)}
        out["probes"] = {p: _probe(fs, p) for p in (
            "/staging/run-0001", "/staging/run-0000", "/staging/run-0001/_tmp", "/staging",
            "/warehouse/dim_customer", "/warehouse/dim_customer/part-0000.parquet", NEIGHBOURS[0])}
        out["n_store"] = len(fs.store)
        out["store_sha256"] = _store_digest(fs)
        out["pseudo_dirs"] = sorted(fs.pseudo_dirs)
        return out
    if case == "edges":
        if size != 1:
            raise ValueError("edges takes size 1")
        return _edges(fs)
    raise ValueError("unsupported case")


def _populate(fs):
    _reset(fs)
    fs.pipe({"/a/b/f1": b"1", "/a/b/c/f2": b"2", "/a/bc/f3": b"3", "/root.txt": b"r",
             "/x/y/z/f4": b"4", "/a/b/c/d/f5": b"5"})
    fs.mkdir("/a/b/empty")
    fs.mkdir("/a/b/c/empty2")
    fs.makedirs("/m/n/o", exist_ok=True)


RM_SCENARIOS = (
    (("/a/b/f1",), {}),
    (("/a/b",), {"recursive": True}),
    (("/x",), {"recursive": True}),
    (("/nope",), {}),
    (("/nope",), {"recursive": True}),
    (("/a/b",), {}),
    (("/x/y",), {}),
    (("/a/b",), {"recursive": True, "maxdepth": 1}),
    ((["/a/b/f1", "/a/bc"],), {"recursive": True}),
    ((["/a/b/f1", "/nope/f9"],), {}),
    (("/a/b/",), {"recursive": True}),
    (("/root.txt",), {}),
    (("/m",), {"recursive": True}),
    (("/m/n/o",), {}),
    (("/a/b/empty",), {}),
    (("/a",), {"recursive": True, "maxdepth": 2}),
    (("memory://a/bc",), {"recursive": True}),
    ((["/a/b/c/f2", "/a/b/c/d/f5", "/a/b/c"],), {"recursive": True}),
    (("/a/b/c/d",), {"recursive": True}),
    (("/",), {"recursive": True}),
)

PROBE_PATHS = ("", "/", "/a", "/a/b", "/a/b/f1", "/a/b/f1/", "memory://a/b/f1", "/a/b/empty",
               "/a/b/c/d", "/a/bc", "/a/bc/f3", "/m/n", "/root.txt", "/nope", "/a/b/f", "/x/y/z")


def _edges(fs):
    out = {"rm": [], "probes": {}, "writes": []}
    for args, kwargs in RM_SCENARIOS:
        _populate(fs)
        result = _call(fs.rm, *args, **kwargs)
        out["rm"].append({"call": [repr(args), sorted(kwargs.items())], "result": result, "after": _snap(fs)})
    _populate(fs)
    out["probes"] = {p: _probe(fs, p) for p in PROBE_PATHS}
    writes = (
        ("pipe_under_file", lambda: fs.pipe("/a/b/f1/child", b"x")),
        ("pipe_deep_under_file", lambda: fs.pipe("/root.txt/q/r", b"x")),
        ("open_pseudo_dir", lambda: fs.open("/a/b/empty", "wb").close()),
        ("pipe_into_pseudo_dir", lambda: fs.pipe("/m/n/o/new.bin", b"new")),
        ("pipe_overwrite", lambda: fs.pipe("/a/bc/f3", b"33")),
        ("mkdir_under_file", lambda: fs.mkdir("/a/b/f1/sub")),
        ("mkdir_existing_file", lambda: fs.mkdir("/root.txt")),
        ("touch_new", lambda: fs.touch("/t/u/v.txt")),
    )
    for name, func in writes:
        out["writes"].append([name, _call(func)])
    out["after_writes"] = _snap(fs)
    out["after_writes_sha256"] = _store_digest(fs)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
