"""Fresh-child workload adapter; result and diagnostics remain untrusted data."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

from generic_meter import GenericMeter


def main(workload, source, config, enabled=True):
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    # Trusted adapter import/setup excluded from counts but included in the
    # parent-owned whole-worker timing boundary. Target package is NOT preloaded.
    spec = importlib.util.spec_from_file_location("trusted_workload", Path(workload))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    meter = GenericMeter(source, config["target_paths"],
                         config.get("package_paths", ["janitor"]),
                         config.get("pandas_udf", True)) if enabled else None
    if meter:
        meter.start()
    try:
        result = module.run(args.case, args.size, args.seed)
    finally:
        measured = meter.finish() if meter else None
    if not isinstance(result, dict):
        raise TypeError("workload.run must return an object")
    print(json.dumps({"schema_version": 1, "result": result, "meter": measured,
                      "python": sys.version}, allow_nan=False, separators=(",", ":")))
