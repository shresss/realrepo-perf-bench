"""Public profiling aid: kerchunk-style reference reads through fsspec's ReferenceFileSystem.

run(case, size, seed) builds a deterministic virtual-dataset reference set (chunk references into
large remote files), opens it with the REAL public fsspec.implementations.reference.ReferenceFileSystem
and fetches the requested keys with ONE public fs.cat(...) call. No timers live here.

The remote object store is a small in-process stand-in (ObjectStore below, owned by this aid, not by
fsspec): every byte range ReferenceFileSystem asks it for is logged, so the observables include both
the bytes returned per key and the set of byte ranges requested from the store (the coalesced fetch
plan). Requested ranges are normalized: a missing start means 0 and a missing end means end of file.
"""
import argparse
import asyncio
import base64
import hashlib
import json

DEFAULT_MAX_GAP = 64_000
DEFAULT_MAX_BLOCK = 256_000_000
RAW_LIMIT = 64  # raw values / ranges are reported only for small results


def payload(fid, length):
    """Deterministic file contents: a 251-byte period depending on the file id."""
    pattern = bytes((i * 7 + fid) % 251 for i in range(251))
    return (pattern * (length // 251 + 1))[:length]


def make_fixture(case, size, seed):
    """Return (files {url: (fid, length)}, refs {key: ref}, keys, options, on_error)."""
    if type(size) is not int or size < 0 or size > 50_000:
        raise ValueError("size must be an integer in 0..50000")
    if type(seed) is not int or not 0 <= seed < 1_000_000:
        raise ValueError("seed must be an integer in 0..999999")
    files, refs, options, on_error = {}, {}, {}, "raise"

    def add_file(url, fid, length):
        files[url] = (fid, length)

    if case == "variable":
        # Monthly NetCDF files of one climate variable, chunks laid out in order with small gaps.
        nfiles = 6
        per = size // nfiles
        for f in range(nfiles):
            url = f"objstore://archive/tas_2025{f + 1:02d}.nc"
            off = 4096
            for c in range(per):
                length = 2000 + (c * 37 + f * 101 + seed * 53) % 4001
                gap = 64 + (c * 13 + f + seed) % 512
                refs[f"tas/{f}.{c}"] = [url, off, length]
                off += length + gap
            add_file(url, f, off)
        keys = sorted(refs, key=lambda k: (((int(k.split(".")[1]) * 7919 + seed) % 6007), k))
    elif case == "single_file":
        # One large HDF5 file holding a whole year of chunks; memory-bounded fetch blocks.
        url = "objstore://archive/pr_2025.h5"
        off = 8192
        for c in range(size):
            length = 1500 + (c * 53 + seed * 7) % 5001
            gap = 32 + (c * 29 + seed) % 900
            refs[f"pr/0.{c}"] = [url, off, length]
            off += length + gap
        add_file(url, 9, off)
        options = {"max_block": 1_048_576}
        keys = sorted(refs, key=lambda k: (((int(k.split(".")[1]) * 4099 + seed) % 8191), k))
    elif case == "overlap":
        # Each reference starts inside the previous one (shared halo bytes).
        for f in range(2):
            url = f"objstore://halo/part{f}.bin"
            start = 1000
            last_end = 0
            for c in range(size):
                length = 400 + (c * 11 + seed + f) % 200
                refs[f"h{f}/{c}"] = [url, start, length]
                last_end = max(last_end, start + length)
                start += 300 + (c * 7 + seed) % 50
            add_file(url, 20 + f, last_end + 500)
        keys = sorted(refs, reverse=True)
    elif case == "nested":
        # Chunk references plus small header references nested inside chunks.
        for f in range(2):
            url = f"objstore://nested/file{f}.nc"
            off = 512
            for c in range(size):
                length = 600 + (c * 17 + seed + f) % 300
                refs[f"n{f}/chunk{c}"] = [url, off, length]
                inner = off + 1 + (c + seed) % 5
                refs[f"n{f}/hdr{c}"] = [url, inner, 16 + (c * 3 + seed) % 40]
                off += length + 100 + (c * 5 + seed) % 200
            add_file(url, 30 + f, off)
        keys = sorted(refs)
    elif case == "chain_block":
        # Overlapping chain with a small max_block (blocks must split), second file with gaps.
        url = "objstore://chain/a.bin"
        for c in range(size):
            refs[f"a/{c}"] = [url, c * 90 + seed % 7, 120]
        add_file(url, 40, size * 90 + 400)
        url2 = "objstore://chain/b.bin"
        for c in range(size):
            refs[f"b/{c}"] = [url2, c * 300, 100 + (c + seed) % 50]
        add_file(url2, 41, size * 300 + 400)
        options = {"max_gap": 0, "max_block": 600}
        keys = sorted(refs)
    elif case == "gaps":
        # Alternating small and large gaps against a 100-byte max_gap; some adjacent ranges.
        url = "objstore://gaps/g.bin"
        off = 0
        for c in range(size):
            length = 80 + (c * 13 + seed) % 40
            refs[f"g/{c}"] = [url, off, length]
            off += length + (0, 50, 150, 100, 101)[(c + seed) % 5]
        add_file(url, 50, off + 10)
        options = {"max_gap": 100}
        keys = sorted(refs)
    elif case == "whole":
        # Whole-file references mixed with ranges in the same and in other files.
        a, b, c3 = "objstore://w/a.bin", "objstore://w/b.bin", "objstore://w/c.bin"
        add_file(a, 60, 3000 + seed % 100)
        add_file(b, 61, 5000)
        add_file(c3, 62, 1234)
        refs["a/all"] = [a]
        for c in range(size):
            refs[f"a/{c}"] = [a, 10 + c * 97, 50]
            refs[f"b/{c}"] = [b, 7 + c * 113 + seed % 11, 60]
        refs["c/all"] = [c3]
        keys = sorted(refs)
    elif case == "inline":
        # Inline (raw and base64) references mixed with ranges.
        url = "objstore://inline/x.bin"
        for c in range(size):
            refs[f"x/{c}"] = [url, 33 + c * 200, 150 + (c + seed) % 30]
            if c % 3 == 0:
                refs[f"x/raw{c}"] = f"raw-{c}-{seed}"
            if c % 4 == 1:
                text = f"inline payload {c} {seed}".encode()
                refs[f"x/b64_{c}"] = "base64:" + base64.b64encode(text).decode()
        add_file(url, 70, 33 + size * 200 + 300)
        keys = sorted(refs, reverse=True)
    elif case == "zero_len":
        # Zero-length references placed inside the gaps between chunks.
        url = "objstore://z/z.bin"
        off = 64
        for c in range(size):
            length = 300 + (c * 19 + seed) % 100
            refs[f"z/{c}"] = [url, off, length]
            refs[f"z/empty{c}"] = [url, off + length + 3, 0]
            off += length + 20
        add_file(url, 80, off + 64)
        keys = sorted(refs)
    elif case == "missing":
        # Missing keys reported in place with on_error="return".
        url = "objstore://m/m.bin"
        for c in range(size):
            refs[f"m/{c}"] = [url, c * 500 + seed % 13, 200]
        add_file(url, 90, size * 500 + 300)
        keys = sorted(refs) + ["m/not-there", "zzz/also-missing"]
        on_error = "return"
    elif case == "single_key":
        # A single key passed as a string returns bytes, not a dict.
        url = "objstore://s/s.bin"
        for c in range(max(size, 1)):
            refs[f"s/{c}"] = [url, 17 + c * 100, 70]
        add_file(url, 95, 17 + max(size, 1) * 100 + 100)
        keys = f"s/{(seed % max(size, 1))}"
    elif case == "empty":
        url = "objstore://e/e.bin"
        for c in range(size):
            refs[f"e/{c}"] = [url, c * 100, 50]
        add_file(url, 99, size * 100 + 100)
        keys = []
    else:
        raise ValueError(f"unsupported case {case!r}")
    return files, refs, keys, options, on_error


def _value_token(value):
    if isinstance(value, bytes):
        return value
    return ("EXC:" + type(value).__name__).encode()


def summarize(result, ranges):
    """Normalize a cat() result plus the logged fetch ranges into JSON-able observables."""
    out = {}
    if isinstance(result, bytes):
        out["kind"] = "bytes"
        out["n"] = 1
        out["digest"] = hashlib.sha256(result).hexdigest()
        out["raw"] = result.hex() if len(result) <= 4096 else None
    else:
        out["kind"] = "dict"
        out["n"] = len(result)
        h = hashlib.sha256()
        for key in sorted(result):
            h.update(key.encode())
            h.update(b"\0")
            h.update(_value_token(result[key]))
            h.update(b"\1")
        out["digest"] = h.hexdigest()
        out["raw"] = ({k: _value_token(result[k]).hex() for k in sorted(result)}
                      if len(result) <= RAW_LIMIT else None)
    plan = sorted(ranges)
    h = hashlib.sha256()
    for path, start, end in plan:
        h.update(f"{path}|{start}|{end}\n".encode())
    out["ranges_count"] = len(plan)
    out["ranges_sha256"] = h.hexdigest()
    out["requested_bytes"] = sum(end - start for _, start, end in plan)
    out["ranges"] = [list(r) for r in plan] if len(plan) <= RAW_LIMIT else None
    return out


def run(case, size, seed):
    files, refs, keys, options, on_error = make_fixture(case, size, seed)

    from fsspec.asyn import AsyncFileSystem
    from fsspec.implementations.reference import ReferenceFileSystem

    blobs = {url.split("://", 1)[1]: payload(fid, length) for url, (fid, length) in files.items()}
    log = []

    class ObjectStore(AsyncFileSystem):
        """In-process remote object store stand-in; logs every requested byte range.

        Declared async-capable (like s3fs/gcsfs) so ReferenceFileSystem uses it directly, but it
        serves the synchronous cat_file/cat_ranges calls itself, in the calling thread.
        """

        protocol = ("objstore",)
        cachable = False

        def _read(self, path, start, end):
            key = path.split("://", 1)[1] if "://" in path else path
            data = blobs[key]
            lo = 0 if start is None else start
            hi = len(data) if end is None else end
            if lo < 0 or hi < 0:
                raise ValueError("negative offsets are not used by this store")
            log.append((key, lo, hi))
            return data[lo:hi]

        def cat_file(self, path, start=None, end=None, **kwargs):
            return self._read(path, start, end)

        def cat_ranges(self, paths, starts, ends, max_gap=None, on_error="return", **kwargs):
            if not isinstance(starts, list):
                starts = [starts] * len(paths)
            if not isinstance(ends, list):
                ends = [ends] * len(paths)
            result = []
            for p, s, e in zip(paths, starts, ends):
                try:
                    result.append(self._read(p, s, e))
                except Exception as exc:  # noqa: BLE001 - mirrors AbstractFileSystem.cat_ranges
                    if on_error == "return":
                        result.append(exc)
                    else:
                        raise
            return result

        def _open(self, path, mode="rb", **kwargs):
            raise NotImplementedError("reads go through cat_file/cat_ranges")

    # ReferenceFileSystem and the store are AsyncFileSystems; by default their constructors start
    # fsspec's shared IO-loop thread. The graded worker sandbox allows no extra threads and the
    # synchronous cat() path below never runs a coroutine, so both get an idle, never-started loop.
    idle_loop = asyncio.new_event_loop()
    store = ObjectStore(loop=idle_loop)
    fs = ReferenceFileSystem(
        {"version": 1, "refs": refs},
        fs=store,
        loop=idle_loop,
        max_gap=options.get("max_gap", DEFAULT_MAX_GAP),
        max_block=options.get("max_block", DEFAULT_MAX_BLOCK),
        skip_instance_cache=True,
    )
    try:
        result = fs.cat(list(keys) if isinstance(keys, list) else keys, on_error=on_error)
    except Exception as exc:  # noqa: BLE001 - reported as an observable
        return {"kind": "raised:" + type(exc).__name__}
    return summarize(result, log)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
