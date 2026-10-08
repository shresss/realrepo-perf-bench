"""Independent oracle for ibis-8445 (stdlib only; never imports ibis, duckdb or pandas).

Rebuilds the seeded wide meter table exactly as workload.py does, evaluates the same rollups in plain Python
(left-deep sums in the same order, SQL null propagation, WHERE filter, GROUP BY meter_id, ORDER BY meter_id), and
writes the default expression names upstream ibis 8.0 produces for left-deep chains:
  Field -> "hNN"; Add(a, b) -> "Add(<a>, <b>)"; Multiply(field, literal) -> "Multiply(hNN, <repr(rate)>)";
  NotNull(field) -> "NotNull(hNN)"; And(a, b) -> "And(<a>, <b>)".
Aggregates are compared with a tight relative tolerance (DuckDB may sum/average in a different order); every
other field (row keys, counts, names, column lists, metadata) must match exactly.
"""

import math
import random

TOU_RATES = (0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.14, 0.19, 0.19, 0.16, 0.14, 0.14,
             0.14, 0.14, 0.14, 0.16, 0.21, 0.27, 0.27, 0.27, 0.21, 0.16, 0.14, 0.11)
METERS = 97
NAME_LIMIT = 16


def rows_for(size):
    return 20000 if size >= 20 else 600


def _columns(size, seed):
    if type(size) is not int or not 1 <= size <= 24:
        raise ValueError("size must be an integer between 1 and 24")
    if type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("seed must be an integer between 0 and 999999")
    rng = random.Random(seed)
    hours = [f"h{i:02d}" for i in range(size)]
    meter, day, values = [], [], {h: [] for h in hours}
    for r in range(rows_for(size)):
        meter.append(r % METERS)
        day.append(r // METERS)
        for h in hours:
            v = rng.random()
            values[h].append(None if v < 0.01 else round(v * 3.0, 3))
    return hours, meter, day, values


def _chain(op, leaves):
    name = leaves[0]
    for leaf in leaves[1:]:
        name = f"{op}({name}, {leaf})"
    return name


def _left_sum(items):
    if any(x is None for x in items):
        return None
    total = items[0]
    for x in items[1:]:
        total = total + x
    return total


def _mean(xs):
    return math.fsum(xs) / len(xs)


def expected(case, size, seed):
    if case not in ("daily", "tariff"):
        raise ValueError("unsupported case")
    hours, meter, day, values = _columns(size, seed)
    n = len(meter)
    out = {"case": case, "size": size, "seed": seed, "rows": rows_for(size)}
    groups = {}
    if case == "daily":
        window = hours[-3:]
        for r in range(n):
            total = _left_sum([values[h][r] for h in hours])
            peak = _left_sum([values[h][r] for h in window])
            if total is None or not total > size * 1.4:
                continue
            g = groups.setdefault(meter[r], [0, [], []])
            g[0] += 1
            g[1].append(total)
            # peak / total: SQL NULL if peak is NULL
            g[2].append(None if peak is None else peak / total)
        result = []
        for m in sorted(groups):
            cnt, totals, shares = groups[m]
            present = [s for s in shares if s is not None]
            result.append([m, cnt, _mean(totals), _mean(present) if present else None])
        out["result"] = result
        out["columns"] = ["meter_id", "days", "mean_kwh", "peak_share"]
        names = [_chain("Add", hours), _chain("Add", window)]
    else:
        for r in range(n):
            row = [values[h][r] for h in hours]
            if any(x is None for x in row):
                continue
            cost = row[0] * TOU_RATES[0]
            for i in range(1, size):
                cost = cost + row[i] * TOU_RATES[i]
            g = groups.setdefault(meter[r], [0, []])
            g[0] += 1
            g[1].append(cost)
        out["result"] = [[m, groups[m][0], math.fsum(groups[m][1]), max(groups[m][1])] for m in sorted(groups)]
        out["columns"] = ["meter_id", "complete_days", "cost", "max_cost"]
        names = [_chain("Add", [f"Multiply({h}, {TOU_RATES[i]!r})" for i, h in enumerate(hours)]),
                 _chain("And", [f"NotNull({h})" for h in hours])]
    if size <= NAME_LIMIT:
        out["default_names"] = names
        out["select_columns"] = ["meter_id", names[0]]
    return out


def _close(a, b):
    if b is None:
        return a is None
    if type(b) is int:
        return type(a) is int and a == b
    return (type(a) in (int, float) and math.isfinite(a)
            and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9))


def equivalent(actual, want):
    if not isinstance(actual, dict) or set(actual) != set(want):
        return False
    if any(actual[k] != want[k] for k in want if k != "result"):
        return False
    a, w = actual["result"], want["result"]
    if not isinstance(a, list) or len(a) != len(w):
        return False
    for ra, rw in zip(a, w):
        if not isinstance(ra, list) or len(ra) != len(rw):
            return False
        if ra[0] != rw[0] or type(ra[0]) is not int or ra[1] != rw[1] or type(ra[1]) is not int:
            return False
        if not all(_close(x, y) for x, y in zip(ra[2:], rw[2:])):
            return False
    return True
