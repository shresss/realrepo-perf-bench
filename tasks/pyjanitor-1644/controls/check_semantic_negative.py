"""Prove ordinary functional defects produce clean output mismatches, not crashes.

This author-only checker runs selected existing cases of size <=64, records the
candidate CLI's real exit status, and succeeds only when every named expected
failure is an output mismatch with normal exit. It never grades performance.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expect-failure-case", action="append", required=True)
    args = parser.parse_args()
    task = args.task.resolve()
    repo = args.repo.resolve()
    spec = importlib.util.spec_from_file_location("protected_expected", task / "expected.py")
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    cases = {case["id"]: case for case in json.loads((task / "cases.json").read_text())}
    observations = []
    for case_id in args.expect_failure_case:
        case = cases[case_id]
        assert case["role"] == "semantic" and 0 <= case["size"] <= 64
        expected = oracle.expected(case["case"], case["size"], case["seed"])
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run(
            [sys.executable, str(task / "workload.py"), "--case", case["case"],
             "--size", str(case["size"]), "--seed", str(case["seed"])],
            cwd=repo, env=env, capture_output=True, text=True, timeout=20,
        )
        try:
            actual = json.loads(process.stdout)
            parse_error = None
        except (ValueError, TypeError) as exc:
            actual = None
            parse_error = str(exc)
        mismatch = process.returncode == 0 and parse_error is None and actual != expected
        observations.append({
            "id": case_id, "case": case["case"], "size": case["size"],
            "seed": case["seed"], "candidate_exit_code": process.returncode,
            "parse_error": parse_error, "expected_semantic_rejection": mismatch,
            "actual": actual, "expected": expected, "stderr": process.stderr,
        })
    passed = all(row["expected_semantic_rejection"] for row in observations)
    print(json.dumps({
        "label": args.label, "repo": str(repo), "interpreter": sys.executable,
        "check_kind": "ordinary_semantic_negative_only", "no_performance_measurement": True,
        "score_eligible": False, "model_reward": None, "task_accepted": False,
        "expected_failure_cases": args.expect_failure_case,
        "all_expected_semantic_rejections_observed": passed,
        "checker_exit_code": 0 if passed else 1, "observations": observations,
    }, allow_nan=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
