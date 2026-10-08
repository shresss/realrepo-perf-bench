"""Real MathFeatures API workload; no expected answers or grading in worker."""
import argparse
import json
import math
import random


def run(case, size, seed):
    import numpy as np
    import pandas as pd
    from feature_engine.creation import MathFeatures

    mode, layout = case.split(":")
    if size < 1:
        raise ValueError("MathFeatures fitting requires at least one row")
    columns = ["a", "b", "c", "d", "e"]
    rng = random.Random(seed)
    values = []
    for i in range(size):
        row = []
        for j in range(5):
            value = rng.randrange(-4096, 4097)
            if mode != "nullable":
                value /= 16
            missing = layout == "missing" and (i % 13 == 0 or (i + j) % 11 == 0)
            row.append(None if missing else value)
        values.append(row)
    X = pd.DataFrame(values, columns=columns, dtype="Int64" if mode == "nullable" else "float64")
    X.index = pd.Index([41 + 3 * (i % 11) for i in range(size)], name="record_id")
    X["untouched"] = [f"payload-{i % 17}" for i in range(size)]
    before = X.copy(deep=True)
    names = ["sum", "mean", "std", "var", "min", "max", "prod", "median"]
    if mode == "speed":
        functions = names = ["sum", "mean", "std"]
    elif mode == "numpy":
        functions = [np.sum, np.mean, np.std, np.var, np.min, np.max, np.prod, np.median]
    elif mode == "custom":
        def spread(row):
            return row.max() - row.min()
        functions, names = spread, ["spread"]
    elif mode == "nullable":
        functions = names = ["sum", "mean"]
    elif mode == "named":
        functions = names
    else:
        raise ValueError(mode)
    outputs = [f"result_{name}" for name in names]
    drop = layout == "drop"
    transformer = MathFeatures(variables=columns, func=functions,
        new_variables_names=outputs, missing_values="ignore", drop_original=drop)
    result = transformer.fit_transform(X)
    numeric = [[None if pd.isna(x) else float(x) for x in row]
               for row in result[outputs].itertuples(index=False, name=None)]
    if any(x is not None and not math.isfinite(x) for row in numeric for x in row):
        raise ValueError("Unexpected non-finite output outside missing-value contract")
    retained = ["untouched"] if drop else columns + ["untouched"]
    return {"values": numeric, "columns": result.columns.tolist(),
            "index": [int(x) for x in result.index], "index_name": result.index.name,
            "input_unchanged": X.equals(before),
            "original_output_unchanged": result[retained].equals(before[retained]),
            "feature_names": list(transformer.get_feature_names_out()),
            "n_features_in": int(transformer.n_features_in_)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    out = run(args.case, args.size, args.seed)
    if len(out["values"]) > 8:
        out = dict(out, values=out["values"][:8], values_truncated_rows=len(out["values"]))
    print(json.dumps(out, allow_nan=False, sort_keys=True))
