"""Independent stdlib oracle for the not-equal keep-first/last join; imports no candidate code.

Semantics (pyjanitor single "!=" condition): right row r matches left row l unless both keys are present and equal
(a missing key on either side is unequal to everything). keep="first"/"last" keeps, per matched left row, the first /
last matching right row in original right order. Output rows follow the order of the materialized not-equal join:
(1) present left keys below the largest present right key, in left order; (2) remaining present left keys above the
smallest present right key; (3) missing left keys, when any right key is present; (4) when any right key is missing,
every left row not yet emitted. Columns: left columns then right columns, fresh RangeIndex.
"""
import hashlib
import json
import random
import struct

PAIR_VARIANTS = {
    "clean": (lambda n: n // 2 + 3, 4, {}),
    "nulls": (lambda n: n // 2 + 5, 4, {"null_every": 4}),
    "allsame": (lambda n: n // 2 + 2, 3, {"all_same": True}),
    "firstnull": (lambda n: n // 2 + 2, 3, {"first_null": True}),
    "firstnull-nulls": (lambda n: n // 2 + 2, 3, {"first_null": True, "null_every": 4}),
    "onecode": (lambda n: n // 2 + 2, 1, {}),
    "onecode-nulls": (lambda n: n // 2 + 6, 1, {"null_every": 4}),
    "grouped": (lambda n: n // 2 + 7, 5, {"null_every": 4, "grouped": True}),
    "datetime": (lambda n: n // 2 + 4, 5, {"null_every": 5, "dtype": "datetime"}),
    "int64": (lambda n: n // 2 + 4, 5, {"null_every": 4, "dtype": "Int64"}),
    "rightempty": (lambda n: 0, 3, {}),
    "rightallnull": (lambda n: 6, 3, {"right_all_null": True}),
    "wide": (lambda n: 3, 40, {"null_every": 6}),
}
SUITE_SIZES = (0, 1, 2, 3, 5, 9, 17, 23, 47, 64)
COLUMNS = ["origin_region", "shipment_id", "weight", "slot_region", "slot_id", "carrier"]


def keys(n_left, n_right, n_codes, seed, null_every=0, first_null=False, dtype="float64", all_same=False,
         grouped=False, right_all_null=False):
    rng = random.Random(seed)
    lv = [rng.randrange(n_codes) for _ in range(n_left)]
    rv = [rng.randrange(n_codes) for _ in range(n_right)]
    if all_same:
        rv = [lv[0] if lv else 0] * n_right
    lv = [float(x) for x in lv]
    rv = [float(x) for x in rv]
    if null_every:
        lv = [None if i % null_every == 3 else x for i, x in enumerate(lv)]
        rv = [None if i % (null_every + 2) == 5 else x for i, x in enumerate(rv)]
    if first_null and rv:
        rv[0] = None
        rv[-1] = None
    if right_all_null:
        rv = [None] * n_right
    if grouped:
        present = sorted(x for x in rv if x is not None)
        rv = present + [None] * (len(rv) - len(present))
    return lv, rv, dtype


def select(lv, rv, keep):
    """Return [(left_pos, right_pos)] in output order using a direct scan per distinct left key."""
    order = range(len(rv)) if keep == "first" else range(len(rv) - 1, -1, -1)
    cache = {}

    def match(value):
        if value not in cache:
            cache[value] = next((j for j in order if value is None or rv[j] is None or rv[j] != value), None)
        return cache[value]

    present = [x for x in rv if x is not None]
    seen = [False] * len(lv)
    sequence = []
    if present:
        high, low = max(present), min(present)
        for i, x in enumerate(lv):
            if x is not None and x < high:
                sequence.append(i)
                seen[i] = True
        for i, x in enumerate(lv):
            if not seen[i] and x is not None and x > low:
                sequence.append(i)
                seen[i] = True
        for i, x in enumerate(lv):
            if not seen[i] and x is None:
                sequence.append(i)
                seen[i] = True
    if len(present) < len(rv):
        sequence.extend(i for i in range(len(lv)) if not seen[i])
    pairs = []
    for i in sequence:
        j = match(lv[i])
        if j is None:
            raise AssertionError("ordering emitted a row without a match")
        pairs.append((i, j))
    return pairs


def join_record(lv, rv, dtype, keep, small):
    pairs = select(lv, rv, keep)
    key_type = {"float64": "float64", "Int64": "Int64", "datetime": "datetime64[s]"}[dtype]
    carrier_type = "str" if rv else "float64"
    meta = [keep, len(pairs), 6, COLUMNS, [key_type, "int64", "float64", key_type, "int64", carrier_type], True]
    h = hashlib.sha256(json.dumps(meta, separators=(",", ":")).encode())
    n = len(pairs)
    sid = [i for i, _ in pairs]
    slot = [j for _, j in pairs]

    def norm(value):
        return -1.0 if value is None else float(value)

    h.update(struct.pack("<%dq" % n, *sid))
    h.update(struct.pack("<%dq" % n, *slot))
    h.update(struct.pack("<%dd" % n, *[i * 0.5 for i in sid]))
    h.update(struct.pack("<%dd" % n, *[norm(lv[i]) for i in sid]))
    h.update(struct.pack("<%dd" % n, *[norm(rv[j]) for j in slot]))
    h.update("\n".join(f"c{j % 13}" for j in slot).encode())
    rows = [[i, j] for i, j in pairs] if small else None
    return {"keep": keep, "meta": meta, "sha256": h.hexdigest()}, rows, n


def expected(case, size, seed):
    joins = []
    if case in ("window", "grouped"):
        for day in range(size):
            nulls = 50 if day % 2 else 0
            if case == "window":
                lv, rv, dtype = keys(12000, 2500, 40, seed=seed + 1000 * day + nulls, null_every=nulls)
            else:
                lv, rv, dtype = keys(12000, 2500, 6, seed=seed + 1000 * day + nulls, null_every=nulls, grouped=True)
            for keep in ("first", "last"):
                joins.append(join_record(lv, rv, dtype, keep, small=False))
    elif case.startswith("pair:"):
        _, keep, variant = case.split(":")
        n_right, n_codes, options = PAIR_VARIANTS[variant]
        lv, rv, dtype = keys(size, n_right(size), n_codes, seed=seed, **options)
        joins.append(join_record(lv, rv, dtype, keep, small=True))
    elif case.startswith("suite:"):
        _, keep = case.split(":")
        for variant in sorted(PAIR_VARIANTS):
            n_right, n_codes, options = PAIR_VARIANTS[variant]
            for n in SUITE_SIZES:
                if n > size:
                    continue
                for offset in range(3):
                    lv, rv, dtype = keys(n, n_right(n), n_codes, seed=seed + offset, **options)
                    joins.append(join_record(lv, rv, dtype, keep, small=False))
    else:
        raise ValueError(f"unknown case: {case}")
    digest = hashlib.sha256()
    for record, _, _ in joins:
        digest.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    return {
        "joins": len(joins),
        "rows": sum(count for _, _, count in joins),
        "sha256": digest.hexdigest(),
        "first_join": joins[0][0] if joins else None,
        "pairs": joins[0][1] if case.startswith("pair:") else None,
        "inputs_unchanged": True,
    }
