"""Protected oracle for the BruteForceSampler sweep task. Standard library only; never imports
Optuna, NumPy or the workload.

Two layers, both required:

1. Independent semantic invariants recomputed here from (case, size, seed) with Decimal grid
   enumeration and the objectives restated in plain Python: trial numbering, parameter names and
   on-grid values, exact objective values, trial states (pruned / failed / NaN-valued), enqueued
   trials honoured in order, every configuration of an exhaustive space visited exactly once, and
   the study stopping exactly at the trial that exhausts the space (no earlier, no later).
2. The exact seeded trial sequence. BruteForceSampler documents `seed` as fixing the search order,
   so for a given seed the ordered list of trials must stay identical. The sha256 of the canonical
   trial list was recorded from the unmodified baseline (optuna bf732bdb) and confirmed byte-equal
   on the upstream four-PR reference (62ac5ef5) on macOS and in the Linux verifier image.
"""
from decimal import Decimal
import hashlib
import itertools
import json
import math

# (case, size, seed) -> (n_trials, n_complete, sha256 of canonical trials list)
GOLDEN = {
    ("grid", 264, 1): (264, 264, "bdce41406e6da3b66fe1054d1b1b56f85b7a2d0dcd9c8dee697742e0e8bf0856"),
    ("conditional", 96, 2): (96, 96, "fe4766198cc38b14c27669a4e598190f4ac2c8a5f4c9449353a84b96538c1618"),
    ("nan", 180, 3): (180, 180, "b0c6a0788db462c10945cbd55e96fe3a5897b1793f073e5aed337749541f1652"),
    ("failures", 36, 4): (36, 25, "f2d6211931f6c72ff328eb70992efb0d151653fd108501002357df9e39161e4a"),
    ("enqueue", 40, 5): (13, 13, "73b96e73fcd6ad82d68b2d2ceeccd6a5a976b9f9c27a2752641a8bb6da0120c6"),
    ("ask-tell-running", 15, 6): (15, 15, "3c0fde32473c7fb601c0fa0892f158de3ec06fb353aa6e75f419b97941dff81b"),
    ("conditional-aps", 96, 7): (96, 96, "7886b9be454cca82079a23848ad452dabe98b4b9e28c39281ef272c829f26c33"),
    ("grid", 528, 5): (528, 528, "e15b4443dbd7825aca601f430e9e532b241511ab4d15686b7d7b8deba5c7928c"),
    ("grid", 1320, 11): (1320, 1320, "651c26aacb06884d6547345ff8261b0269734e7cf7a34a50bb38d887d43a10c5"),
}


def expected(case, size, seed):
    key = (case, size, seed)
    if key not in GOLDEN:
        raise ValueError("undeclared case")
    n_trials, n_complete, digest = GOLDEN[key]
    return {"case": case, "size": size, "seed": seed, "n_trials": n_trials,
            "n_complete": n_complete, "trials_sha256": digest}


def canonical_digest(trials):
    text = json.dumps(trials, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def steps(low, high, step):
    """Grid values exactly as a Decimal walk from low to high produces them."""
    low, high, step = Decimal(str(low)), Decimal(str(high)), Decimal(str(step))
    out, value = [], low
    while value <= high:
        out.append(float(value))
        value += step
    return out


def show(value):
    return repr("nan" if isinstance(value, float) and math.isnan(value) else value)


def config(params):
    return tuple(sorted((name, show(value)) for name, value in params.items()))


def space(case, size):
    """Return (list of configurations as param dicts, objective(params) -> (state, value))."""
    if case == "grid":
        xs = size // 132
        configs = [{"n_estimators_k": x, "optimizer": o, "dropout": d, "activation": a}
                   for x in range(1, xs + 1) for o in ("sgd", "adam", "rmsprop", "adagrad")
                   for d in steps(0.0, 1.0, 0.1) for a in ("relu", "tanh", "gelu")]

        def objective(p):
            return "COMPLETE", (p["n_estimators_k"] * 0.37 + len(p["optimizer"]) * 1.1
                                - p["dropout"] * 2.3 + len(p["activation"]))
        return configs, objective
    if case in ("conditional", "conditional-aps"):
        configs = ([{"model": "linear", "alpha": a, "penalty": q}
                    for a in steps(0.0, 0.5, 0.05) for q in ("l1", "l2")]
                   + [{"model": "tree", "depth": d, "leaves": v}
                      for d in range(1, 9) for v in range(2, 17, 2)]
                   + [{"model": "knn", "k": k, "weights": w}
                      for k in range(1, 10, 2) for w in ("uniform", "distance")])

        def objective(p):
            if p["model"] == "linear":
                return "COMPLETE", p["alpha"] + (p["penalty"] == "l1")
            if p["model"] == "tree":
                return "COMPLETE", p["depth"] * 0.1 + p["leaves"] * 0.01
            return "COMPLETE", p["k"] + (p["weights"] == "uniform")
        return configs, objective
    if case == "nan":
        weird = [float("inf"), -float("inf"), float("nan"), None, "s", 3]
        configs = [{"a": a, "b": b, "c": c} for a in weird for b in weird
                   for c in steps(-1.0, 1.0, 0.5)]

        def objective(p):
            a, b, c = p["a"], p["b"], p["c"]
            return "COMPLETE", 0.0 if a is None else float(len(repr(a)) + len(repr(b))) + c
        return configs, objective
    if case == "failures":
        configs = [{"x": x, "y": y} for x in range(6) for y in steps(0.25, 1.5, 0.25)]

        def objective(p):
            x, y = p["x"], p["y"]
            if (x + int(y * 4)) % 5 == 0:
                return "PRUNED", None
            if (x * 3 + int(y * 4)) % 7 == 0:
                return "FAIL", None
            if x == 4 and y == 0.5:
                return "FAIL", None
            return "COMPLETE", x - y
        return configs, objective
    if case in ("enqueue", "ask-tell-running"):
        if case == "enqueue":
            configs = [{"x": x, "y": y} for x in range(0, 7, 2) for y in ("a", "b", "c")]

            def objective(p):
                return "COMPLETE", float(p["x"] + ord(p["y"]))
        else:
            configs = [{"x": x, "z": z} for x in range(4) for z in steps(0.0, 0.4, 0.1)]

            def objective(p):
                return "COMPLETE", p["x"] + p["z"]
        return configs, objective
    raise ValueError("unsupported case")


def invariants(case, size, trials):
    configs, objective = space(case, size)
    table = {config(p): objective(p) for p in configs}
    if len(table) != len(configs):
        return False
    seen = []
    for index, row in enumerate(trials):
        if not isinstance(row, list) or len(row) != 4 or row[0] != index:
            return False
        number, state, params, values = row
        key = tuple(tuple(item) for item in params) if isinstance(params, list) else None
        if key is None or any(len(item) != 2 for item in key) or key not in table:
            return False
        want_state, want_value = table[key]
        if state != want_state:
            return False
        if want_value is None:
            if values is not None:
                return False
        elif values != [want_value]:
            return False
        seen.append(key)
    covered = set()
    stop_at = None
    for index, key in enumerate(seen):
        covered.add(key)
        if stop_at is None and len(covered) == len(table):
            stop_at = index + 1
    if case == "enqueue":
        first = [dict(k) for k in seen[:4]]
        if first[:3] != [{"x": "2", "y": "'b'"}, {"x": "6", "y": "'a'"}, {"x": "2", "y": "'b'"}]:
            return False
        if len(first) < 4 or first[3]["x"] != "4":
            return False
        # Stops exactly when the 12-point grid is exhausted, unless n_trials runs out first.
        return len(trials) == (stop_at if stop_at is not None else size) and len(trials) <= size
    if case == "ask-tell-running":
        return len(trials) == size
    # Exhaustive optimize() sweeps: each configuration exactly once, stop exactly at exhaustion.
    return len(trials) == len(table) == size and stop_at == len(trials) and len(set(seen)) == len(seen)


def equivalent(actual, want):
    try:
        if not isinstance(actual, dict) or set(actual) != {"n_trials", "trials", "n_complete"}:
            return False
        trials = actual["trials"]
        if not isinstance(trials, list) or actual["n_trials"] != len(trials):
            return False
        if actual["n_trials"] != want["n_trials"] or actual["n_complete"] != want["n_complete"]:
            return False
        if sum(1 for row in trials if isinstance(row, list) and len(row) == 4
               and row[1] == "COMPLETE") != want["n_complete"]:
            return False
        if not invariants(want["case"], want["size"], trials):
            return False
        return canonical_digest(trials) == want["trials_sha256"]
    except Exception:
        return False
