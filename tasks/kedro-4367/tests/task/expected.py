"""Protected independent oracle. Standard library only; never imports Kedro or the workload.

Derives every resolved value directly from (case, size, seed): nested globals, defaults
(zero, null, missing), base/local environment overrides, runtime parameters, repeated
loads, explicit globals replacement through the public setter, and a fresh loader that
must see the original file-backed globals. Copied from the cache lane's expected.py
(semantics unchanged) plus the digest normalization used by workload.py.
"""
import hashlib
import json

SMALL = 12


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def checkpoints_for(case, size, seed):
    result = []
    for checkpoint in (0, 1, 2, "fresh"):
        generation = checkpoint if case == "globals_replaced" and checkpoint != "fresh" else 0
        explicit = case == "globals_replaced" and checkpoint in (1, 2)
        rows = {}
        catalog = {}
        for index in range(size):
            value_index = (7 * index + seed) % size
            label_index = (11 * index + seed) % size
            rows[f"p{index}"] = {"value": (17 * value_index + seed + 1009 * generation) % 10007,
                                 "label": f"g{generation}-{label_index}-{seed}",
                                 "limit": seed + 3, "default": 0}
            catalog[f"d{index}"] = {"type": "MemoryDataset",
                                    "metadata": {"label": f"g{generation}-{index}-{seed}",
                                                 "limit": seed + 3}}
        parameters = {"rows": rows, "zero": 0, "nullable": None, "missing_null": None,
                      "environment": f"explicit-{generation}" if explicit else "local",
                      "local_only": seed + 1, "settings": {"limit": seed + 3}}
        result.append({"phase": checkpoint, "parameters": parameters, "catalog": catalog})
    return result


def expected(case, size, seed):
    if case not in ("stable", "globals_replaced") or not 2 <= size <= 1000 or not 0 <= seed <= 999:
        raise ValueError("Unsupported case/size/seed")
    points = checkpoints_for(case, size, seed)
    return {"case": case, "size": size, "seed": seed, "checkpoint_count": len(points),
            "phase_sha256": [hashlib.sha256(canonical(point).encode()).hexdigest() for point in points],
            "sha256": hashlib.sha256(canonical(points).encode()).hexdigest(),
            "checkpoints": points if size <= SMALL else None}
