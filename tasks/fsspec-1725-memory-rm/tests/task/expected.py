"""Independent oracle for fsspec-1725-memory-rm. Stdlib only; never imports fsspec or the workload.

cleanup: computed from first principles (which keys survive, their bytes, which directories remain).
edges: golden values of the BASE commit's public behaviour (176efbe0), recorded once by the author on the
untouched base tree and identical on the public reference tree (03e89cc1); fixed literal below, sha256 pinned.
"""
import hashlib
import json

NEIGHBOURS = ("/staging/run-0001-archive/manifest.json", "/staging/run-00010/part-00000.parquet")

EDGES_JSON = '{"after_writes":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/m/n/o/new.bin","/root.txt","/t/u/v.txt","/x/y/z/f4"]},"after_writes_sha256":"4e18d48c60e009e578eb137f9603bc1d29c2b8aff4d26c1cab22209704be0205","probes":{"":[false,true,true,"directory"],"/":[false,true,true,"directory"],"/a":[false,true,true,"directory"],"/a/b":[false,true,true,"directory"],"/a/b/c/d":[false,true,true,"directory"],"/a/b/empty":[false,true,true,"directory"],"/a/b/f":[false,false,false,"FileNotFoundError"],"/a/b/f1":[true,false,true,"file"],"/a/b/f1/":[true,false,true,"file"],"/a/bc":[false,true,true,"directory"],"/a/bc/f3":[true,false,true,"file"],"/m/n":[false,true,true,"directory"],"/nope":[false,false,false,"FileNotFoundError"],"/root.txt":[true,false,true,"file"],"/x/y/z":[false,true,true,"directory"],"memory://a/b/f1":[true,false,true,"file"]},"rm":[{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b/f1\',)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/m","/m/n","/m/n/o"],"store":["/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt"]},"call":["(\'/x\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/nope\',)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/nope\',)",[["recursive",true]]],"result":"FileNotFoundError"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b\',)",[]],"result":"OSError"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/x/y\',)",[]],"result":"FileNotFoundError"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b\',)",[["maxdepth",1],["recursive",true]]],"result":"OSError"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/root.txt","/x/y/z/f4"]},"call":["([\'/a/b/f1\', \'/a/bc\'],)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["([\'/a/b/f1\', \'/nope/f9\'],)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/m","/m/n","/m/n/o"],"store":["/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b/\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/x/y/z/f4"]},"call":["(\'/root.txt\',)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/m\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/m/n/o\',)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b/empty\',)",[]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/root.txt","/x/y/z/f4"]},"call":["(\'/a\',)",[["maxdepth",2],["recursive",true]]],"result":"OSError"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/d/f5","/a/b/c/f2","/a/b/f1","/root.txt","/x/y/z/f4"]},"call":["(\'memory://a/bc\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["([\'/a/b/c/f2\', \'/a/b/c/d/f5\', \'/a/b/c\'],)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":["","/a","/a/b","/a/b/c","/a/b/c/empty2","/a/b/empty","/m","/m/n","/m/n/o"],"store":["/a/b/c/f2","/a/b/f1","/a/bc/f3","/root.txt","/x/y/z/f4"]},"call":["(\'/a/b/c/d\',)",[["recursive",true]]],"result":"ok"},{"after":{"pseudo_dirs":[""],"store":[]},"call":["(\'/\',)",[["recursive",true]]],"result":"ok"}],"writes":[["pipe_under_file","FileExistsError"],["pipe_deep_under_file","FileExistsError"],["open_pseudo_dir","IsADirectoryError"],["pipe_into_pseudo_dir","ok"],["pipe_overwrite","ok"],["mkdir_under_file","NotADirectoryError"],["mkdir_existing_file","FileExistsError"],["touch_new","ok"]]}'
EDGES_SHA256 = "4816a050abcc9422476e9b2cc61e1341d43457d647005cbe85c762a358aadc50"


def _cleanup(size, seed):
    shift = seed % 7
    survivors = {}
    for i in range(size):
        survivors["/warehouse/dim_customer/part-%04d.parquet" % i] = b"d" * ((i + shift) % 31 + 1)
    for j, p in enumerate(NEIGHBOURS):
        survivors[p] = b"keep-%d-%d" % (j, seed)
    h = hashlib.sha256()
    for key in sorted(survivors):
        h.update(key.encode() + b"\0" + survivors[key] + b"\n")
    gone = [False, False, False, "FileNotFoundError"]
    return {
        "rm_manifest": "ok",
        "rm_run": "ok",
        "probes": {
            "/staging/run-0001": gone,
            "/staging/run-0000": gone,
            "/staging/run-0001/_tmp": gone,
            "/staging": [False, True, True, "directory"],
            "/warehouse/dim_customer": [False, True, True, "directory"],
            "/warehouse/dim_customer/part-0000.parquet": [True, False, True, "file"],
            NEIGHBOURS[0]: [True, False, True, "file"],
        },
        "n_store": len(survivors),
        "store_sha256": h.hexdigest(),
        "pseudo_dirs": ["", "/staging"],
    }


def expected(case, size, seed):
    if type(size) is not int or type(seed) is not int or not 0 <= seed < 10**6:
        raise ValueError("size and seed must be integers")
    if case == "cleanup":
        if not 1 <= size <= 5000:
            raise ValueError("size must be in 1..5000")
        return _cleanup(size, seed)
    if case == "edges":
        if size != 1:
            raise ValueError("edges takes size 1")
        if hashlib.sha256(EDGES_JSON.encode()).hexdigest() != EDGES_SHA256:
            raise ValueError("edges golden literal changed")
        return json.loads(EDGES_JSON)
    raise ValueError("unsupported case")
