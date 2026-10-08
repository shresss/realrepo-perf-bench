"""Independent scalar/statistics oracle, importing neither pandas nor candidate."""
import math
import random
import statistics


def reduce_row(values, mode):
    clean = [x for x in values if x is not None]
    n = len(clean)
    mean = statistics.fmean(clean) if n else None
    if mode == "custom":
        return [float(max(clean) - min(clean)) if n else None]
    result = [float(sum(clean)), mean]
    if mode == "nullable":
        return result
    population = mode == "numpy"
    variance = (statistics.pvariance(clean) if population else statistics.variance(clean)) if n > (0 if population else 1) else None
    result += [math.sqrt(variance) if variance is not None else None, variance]
    result += [float(min(clean)) if n else None, float(max(clean)) if n else None,
               float(math.prod(clean)),
               float(statistics.median(clean)) if n and not (population and n < len(values)) else None]
    return result[:3] if mode == "speed" else result


def expected(case, size, seed):
    mode, layout = case.split(":")
    if size < 1:
        raise ValueError("minimum fitting input is one row")
    rows = []
    rng = random.Random(seed)
    for r in range(size):
        data = [rng.randrange(-4096, 4097) / (1 if mode == "nullable" else 16) for _ in range(5)]
        if layout == "missing":
            data = [None if r % 13 == 0 or (r + c) % 11 == 0 else value for c, value in enumerate(data)]
        rows.append(reduce_row(data, mode))
    names = ["sum", "mean", "std", "var", "min", "max", "prod", "median"]
    names = names[:3] if mode == "speed" else names[:2] if mode == "nullable" else ["spread"] if mode == "custom" else names
    columns = ([] if layout == "drop" else ["a", "b", "c", "d", "e"]) + ["untouched"] + [f"result_{name}" for name in names]
    return {"values": rows, "columns": columns,
            "index": [41 + (r % 11) * 3 for r in range(size)], "index_name": "record_id",
            "input_unchanged": True, "original_output_unchanged": True,
            "feature_names": columns, "n_features_in": 6}


def equivalent(actual, expected_value):
    if not isinstance(actual, dict) or actual.keys() != expected_value.keys():
        return False
    for key in expected_value.keys() - {"values"}:
        if type(actual[key]) is not type(expected_value[key]) or actual[key] != expected_value[key]:
            return False
    rows = actual["values"]
    if not isinstance(rows, list) or len(rows) != len(expected_value["values"]):
        return False
    for row, want in zip(rows, expected_value["values"]):
        if not isinstance(row, list) or len(row) != len(want):
            return False
        for value, target in zip(row, want):
            if target is None:
                if value is not None:
                    return False
            elif type(value) not in (float, int) or not math.isfinite(value) or not math.isclose(value, target, rel_tol=1e-10, abs_tol=1e-10):
                return False
    return True


def repeat_seed(seed, repeat):
    """Verifier-only (runtime v1.1-rs): input seed for performance repeat `repeat` >= 1.

    Repeat 0 keeps the declared seed; repeats 1 and 2 get fresh fixtures from the same
    generator and distribution, so a later repeat never replays an earlier input."""
    return seed * 1000 + repeat
