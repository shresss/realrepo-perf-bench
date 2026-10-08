"""Smart-meter interval rollups through the public ibis API (DuckDB backend, in-memory, one thread).

run(case, size, seed): size = number of hourly interval columns in the wide export (1..24).
  daily  : daily consumption = left-deep sum of the hourly columns plus an evening peak window,
           mutate -> filter -> group_by/aggregate -> order_by -> execute.
  tariff : time-of-use cost = left-deep sum of hourly reading x hourly rate, a completeness flag =
           left-deep AND of per-hour notnull checks, filter on completeness -> group_by/aggregate ->
           order_by -> execute.
Observables: per-meter aggregate rows (raw floats, compared with a tolerance), and for sizes <= 20 the
default expression names and the default column names of an unnamed select (exact strings).
"""

import argparse
import json
import random

TOU_RATES = (0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.14, 0.19, 0.19, 0.16, 0.14, 0.14,
             0.14, 0.14, 0.14, 0.16, 0.21, 0.27, 0.27, 0.27, 0.21, 0.16, 0.14, 0.11)
METERS = 97
NAME_LIMIT = 16


def rows_for(size):
    return 20000 if size >= 20 else 600


def make_columns(size, seed):
    if type(size) is not int or not 1 <= size <= 24:
        raise ValueError("size must be an integer between 1 and 24")
    if type(seed) is not int or not 0 <= seed < 1000000:
        raise ValueError("seed must be an integer between 0 and 999999")
    rng = random.Random(seed)
    hours = [f"h{i:02d}" for i in range(size)]
    cols = {"meter_id": [], "day": []}
    for h in hours:
        cols[h] = []
    for r in range(rows_for(size)):
        cols["meter_id"].append(r % METERS)
        cols["day"].append(r // METERS)
        for h in hours:
            v = rng.random()
            cols[h].append(None if v < 0.01 else round(v * 3.0, 3))  # ~1% missing readings
    return hours, cols


def _f(x):
    return None if x is None or x != x else float(x)


def run(case, size, seed):
    if case not in ("daily", "tariff"):
        raise ValueError("unsupported case")
    hours, cols = make_columns(size, seed)
    import ibis
    from ibis import _

    con = ibis.duckdb.connect(threads=1)
    # Materialize generated input without an Arrow input scanner (threadless worker).
    con.create_table("readings", schema=ibis.schema(
        [("meter_id", "int64"), ("day", "int64")] + [(h, "float64") for h in hours]))
    keys = ["meter_id", "day", *hours]
    for start in range(0, rows_for(size), 1000):
        values = ["(" + ",".join("NULL" if cols[k][r] is None else repr(cols[k][r])
                                  for k in keys) + ")"
                  for r in range(start, min(start + 1000, rows_for(size)))]
        con.raw_sql("INSERT INTO readings VALUES " + ",".join(values))
    t = con.table("readings")
    out = {"case": case, "size": size, "seed": seed, "rows": rows_for(size)}
    h = [t[c] for c in hours]
    if case == "daily":
        total = h[0]
        for col in h[1:]:
            total = total + col
        window = h[-3:]
        peak = window[0]
        for col in window[1:]:
            peak = peak + col
        q = (t.mutate(daily_kwh=total, peak_kwh=peak)
              .filter(_.daily_kwh.notnull() & (_.daily_kwh > size * 1.4))
              .group_by("meter_id")
              .aggregate(days=_.count(), mean_kwh=_.daily_kwh.mean(),
                         peak_share=(_.peak_kwh / _.daily_kwh).mean())
              .order_by("meter_id"))
        df = q.execute()
        out["result"] = [[int(m), int(d), _f(x), _f(p)] for m, d, x, p in df.itertuples(index=False)]
        named = (total, peak)
    else:
        cost = h[0] * TOU_RATES[0]
        for i, col in enumerate(h[1:], start=1):
            cost = cost + col * TOU_RATES[i]
        complete = h[0].notnull()
        for col in h[1:]:
            complete = complete & col.notnull()
        q = (t.filter(complete)
              .group_by("meter_id")
              .aggregate(complete_days=_.count(), cost=cost.sum(), max_cost=cost.max())
              .order_by("meter_id"))
        df = q.execute()
        out["result"] = [[int(m), int(d), _f(c), _f(x)] for m, d, c, x in df.itertuples(index=False)]
        named = (cost, complete)
    out["columns"] = list(df.columns)
    if size <= NAME_LIMIT:
        out["default_names"] = [e.get_name() for e in named]
        out["select_columns"] = list(t.select("meter_id", named[0]).columns)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    a = parser.parse_args()
    print(json.dumps(run(a.case, a.size, a.seed), sort_keys=True))
