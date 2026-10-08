"""Public-API join probe. No timing, reward, or expected answers live here."""
import argparse
import hashlib
import json
import random


def run(case, size, seed):
    import numpy as np
    import pandas as pd
    import janitor  # noqa: F401 -- registers the real public DataFrame API

    operator, keep, layout = case.split(":")
    rng = random.Random(seed)
    left_values = [rng.randrange(-max(size, 1), max(size, 1)) for _ in range(size)]
    right_values = [rng.randrange(-max(size, 1), max(size, 1)) for _ in range(size)]
    if layout == "sorted":
        right_values.sort()
    elif layout == "reverse":
        right_values.sort(reverse=True)
    elif layout == "ties":
        left_values = [value % 7 for value in left_values]
        right_values = [value % 7 for value in right_values]
    elif layout == "nulls":
        left_values = [None if i % 11 == 0 else x for i, x in enumerate(left_values)]
        right_values = [None if i % 7 == 0 else x for i, x in enumerate(right_values)]
    elif layout not in {"unsorted", "datetime"}:
        raise ValueError(f"unknown layout: {layout}")
    left = pd.DataFrame({"left_key": pd.Series(left_values, dtype="float64"), "left_id": np.arange(size)})
    right = pd.DataFrame({"right_key": pd.Series(right_values, dtype="float64"), "right_id": np.arange(size)})
    if layout == "datetime":
        left["left_key"] = pd.to_datetime(left["left_key"], unit="D")
        right["right_key"] = pd.to_datetime(right["right_key"], unit="D")
    # Original labels differ from positional first/last and must not be mutated.
    left.index = pd.Index(np.arange(size) * 3 + 41, name="left_original")
    right.index = pd.Index(np.arange(size) * 5 + 73, name="right_original")
    before = [left.to_json(date_format="iso", date_unit="ns", orient="split"), right.to_json(date_format="iso", date_unit="ns", orient="split")]
    result = left.conditional_join(right, ("left_key", "right_key", operator), keep=keep)
    pairs = [[int(a), int(b)] for a, b in result[["left_id", "right_id"]].itertuples(index=False, name=None)]
    after = [left.to_json(date_format="iso", date_unit="ns", orient="split"), right.to_json(date_format="iso", date_unit="ns", orient="split")]
    payload = json.dumps(pairs, separators=(",", ":"))
    return {
        "count": len(pairs),
        "pairs_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "pairs": pairs if size <= 64 else None,
        "input_unchanged": before == after,
        "index_names": [left.index.name, right.index.name],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
