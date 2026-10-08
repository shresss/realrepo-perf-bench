"""Public-API not-equal join probe. No timing, reward, or expected answers live here.

Scenario: nightly shipment re-routing. For each daily partition, every open shipment (left) picks the first or last
bookable carrier slot (right, booking order) whose depot region code differs from the shipment's origin region:
DataFrame.conditional_join(right, ("origin_region", "slot_region", "!="), keep="first"|"last").

Cases:
  window   size = number of daily partitions (12000 shipments x 2500 slots each, 40 region codes, slots in booking
           order; odd days carry ~2% missing region codes). keep first and keep last per partition.
  grouped  same partition shape, 6 region codes, slots listed grouped by depot region (missing codes listed last).
  pair:<keep>:<variant>  one small join, size = number of shipments (edge cases).
  suite:<keep>  every pair variant at sizes 0..size and three seeds, one process (edge-case sweep).
"""
import argparse
import hashlib
import json
import random

PAIR_VARIANTS = {
    # variant: (n_right(size), n_codes, options)
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


def frames(n_left, n_right, n_codes, seed, null_every=0, first_null=False, dtype="float64", all_same=False,
           grouped=False, right_all_null=False):
    import numpy as np
    import pandas as pd
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
    left = pd.DataFrame({"origin_region": pd.Series(lv, dtype="float64"), "shipment_id": np.arange(n_left),
                         "weight": np.arange(n_left) * 0.5})
    right = pd.DataFrame({"slot_region": pd.Series(rv, dtype="float64"), "slot_id": np.arange(n_right),
                          "carrier": [f"c{i % 13}" for i in range(n_right)]})
    if dtype == "Int64":
        left["origin_region"] = left["origin_region"].astype("Int64")
        right["slot_region"] = right["slot_region"].astype("Int64")
    elif dtype == "datetime":
        left["origin_region"] = pd.to_datetime(left["origin_region"], unit="D")
        right["slot_region"] = pd.to_datetime(right["slot_region"], unit="D")
    # Original labels differ from positions and must survive unchanged.
    left.index = pd.Index(np.arange(n_left) * 3 + 41, name="ship_label")
    right.index = pd.Index(np.arange(n_right) * 5 + 73, name="slot_label")
    return left, right


def _key_floats(series):
    import numpy as np
    import pandas as pd
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        missing = series.isna().to_numpy()
        days = series.to_numpy(dtype="datetime64[ns]").astype("int64") // 86_400_000_000_000
        values = days.astype("float64")
        values[missing] = -1.0
        return values
    values = series.to_numpy(dtype="float64", na_value=np.nan)
    return np.where(np.isnan(values), -1.0, values)


def _frame_state(frame):
    import pandas as pd
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()
    return (hashed, list(frame.columns), [str(t) for t in frame.dtypes], frame.index.name)


def join_digest(left, right, keep, small):
    import numpy as np
    import pandas as pd
    before = (_frame_state(left), _frame_state(right))
    try:
        out = left.conditional_join(right, ("origin_region", "slot_region", "!="), keep=keep)
    except Exception as exc:  # identical exception behavior is part of the contract
        record = {"keep": keep, "error": type(exc).__name__}
        return record, None, 0, (before == (_frame_state(left), _frame_state(right)))
    unchanged = before == (_frame_state(left), _frame_state(right))
    meta = [keep, int(out.shape[0]), int(out.shape[1]), [str(c) for c in out.columns], [str(t) for t in out.dtypes],
            isinstance(out.index, pd.RangeIndex) and out.index.start == 0 and out.index.step == 1]
    h = hashlib.sha256(json.dumps(meta, separators=(",", ":")).encode())
    sid = np.ascontiguousarray(out["shipment_id"].to_numpy(dtype="int64"), dtype="<i8")
    slot = np.ascontiguousarray(out["slot_id"].to_numpy(dtype="int64"), dtype="<i8")
    weight = np.ascontiguousarray(out["weight"].to_numpy(dtype="float64"), dtype="<f8")
    origin = np.ascontiguousarray(_key_floats(out["origin_region"]), dtype="<f8")
    slot_region = np.ascontiguousarray(_key_floats(out["slot_region"]), dtype="<f8")
    for block in (sid, slot, weight, origin, slot_region):
        h.update(block.tobytes())
    h.update("\n".join(out["carrier"].tolist()).encode())
    rows = None
    if small:
        rows = [[int(a), int(b)] for a, b in zip(sid.tolist(), slot.tolist())]
    return {"keep": keep, "meta": meta, "sha256": h.hexdigest()}, rows, int(out.shape[0]), unchanged


def run(case, size, seed):
    import janitor  # noqa: F401 -- registers the real public DataFrame API

    joins = []
    if case in ("window", "grouped"):
        for day in range(size):
            nulls = 50 if day % 2 else 0
            if case == "window":
                left, right = frames(12000, 2500, 40, seed=seed + 1000 * day + nulls, null_every=nulls)
            else:
                left, right = frames(12000, 2500, 6, seed=seed + 1000 * day + nulls, null_every=nulls, grouped=True)
            for keep in ("first", "last"):
                joins.append(join_digest(left, right, keep, small=False))
    elif case.startswith("pair:"):
        _, keep, variant = case.split(":")
        n_right, n_codes, options = PAIR_VARIANTS[variant]
        left, right = frames(size, n_right(size), n_codes, seed=seed, **options)
        joins.append(join_digest(left, right, keep, small=True))
    elif case.startswith("suite:"):
        _, keep = case.split(":")
        for variant in sorted(PAIR_VARIANTS):
            n_right, n_codes, options = PAIR_VARIANTS[variant]
            for n in SUITE_SIZES:
                if n > size:
                    continue
                for offset in range(3):
                    left, right = frames(n, n_right(n), n_codes, seed=seed + offset, **options)
                    joins.append(join_digest(left, right, keep, small=False))
    else:
        raise ValueError(f"unknown case: {case}")
    digest = hashlib.sha256()
    for record, _, _, _ in joins:
        digest.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    return {
        "joins": len(joins),
        "rows": sum(count for _, _, count, _ in joins),
        "sha256": digest.hexdigest(),
        "first_join": joins[0][0] if joins else None,
        "pairs": joins[0][1] if case.startswith("pair:") else None,
        "inputs_unchanged": all(flag for _, _, _, flag in joins),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
