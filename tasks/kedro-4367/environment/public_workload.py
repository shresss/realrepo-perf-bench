"""Kedro OmegaConfigLoader workload: real public API, no timing, reward or expected answers here.

A project config directory (base + local environments) is written as ordinary
YAML-compatible JSON files: a globals file with `size` entries, a parameters file with
`size` rows whose values interpolate nested globals and runtime parameters (with
defaults, including zero and null), and a catalog with `size` datasets. The loader is
created once and catalog + parameters are loaded three times. In the `globals_replaced`
case the public `loader["globals"] = mapping` setter replaces the globals before the
second and third loads. A fresh loader is then created on the same files and must see
the original file-backed values. Every resolved value is normalized and digested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

SMALL = 12  # raw checkpoints are returned for size <= SMALL; larger sizes return digests only


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def run(case, size, seed):
    if case not in ("stable", "globals_replaced") or not 2 <= size <= 1000 or not 0 <= seed <= 999:
        raise ValueError("Unsupported case/size/seed")
    from kedro.config import OmegaConfigLoader

    def globals_for(phase):
        return {"entries": {f"v{i}": {"value": (i * 17 + seed + phase * 1009) % 10007,
                                      "label": f"g{phase}-{i}-{seed}"} for i in range(size)},
                "zero": 0, "nullable": None, "environment": f"explicit-{phase}"}

    parameters = {"rows": {f"p{i}": {
        "value": "${globals:entries.v" + str((i * 7 + seed) % size) + ".value}",
        "label": "${globals:entries.v" + str((i * 11 + seed) % size) + ".label}",
        "limit": "${runtime_params:settings.limit,3}",
        "default": "${globals:missing,0}",
    } for i in range(size)}, "zero": "${globals:zero,8}",
        "nullable": "${globals:nullable,8}", "missing_null": "${globals:absent,null}",
        "environment": "${globals:environment}"}
    catalog = {f"d{i}": {"type": "MemoryDataset",
                         "metadata": {"label": "${globals:entries.v" + str(i) + ".label}",
                                      "limit": "${runtime_params:settings.limit}"}}
               for i in range(size)}
    checkpoints = []
    with tempfile.TemporaryDirectory(prefix="kedro-native-") as directory:
        root = Path(directory)
        (root / "base").mkdir()
        (root / "local").mkdir()
        files = {"base/globals.yml": globals_for(0),
                 "local/globals.yml": {"environment": "local"},
                 "base/parameters.yml": parameters,
                 "local/parameters.yml": {"local_only": seed + 1},
                 "base/catalog.yml": catalog}
        for name, value in files.items():
            (root / name).write_text(json.dumps(value))  # JSON is valid YAML.
        loader = OmegaConfigLoader(str(root), base_env="base", default_run_env="local",
                                   runtime_params={"settings": {"limit": seed + 3}})
        for phase in range(3):
            if case == "globals_replaced" and phase:
                loader["globals"] = globals_for(phase)
            checkpoints.append({"phase": phase, "parameters": loader["parameters"],
                                "catalog": loader["catalog"]})
        # A new loader must see the original files, not the prior instance's override.
        fresh = OmegaConfigLoader(str(root), base_env="base", default_run_env="local",
                                  runtime_params={"settings": {"limit": seed + 3}})
        checkpoints.append({"phase": "fresh", "parameters": fresh["parameters"],
                            "catalog": fresh["catalog"]})
    return {"case": case, "size": size, "seed": seed, "checkpoint_count": len(checkpoints),
            "phase_sha256": [hashlib.sha256(canonical(point).encode()).hexdigest() for point in checkpoints],
            "sha256": hashlib.sha256(canonical(checkpoints).encode()).hexdigest(),
            "checkpoints": checkpoints if size <= SMALL else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
