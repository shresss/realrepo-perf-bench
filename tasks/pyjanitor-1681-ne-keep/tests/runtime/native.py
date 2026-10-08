"""Bounded, protected upstream regression selection for pyjanitor PR 1681.

This supplements the parent's independent oracle. Pytest and candidate Python
execute in one child: these reports are NOT a tamper-proof adversarial oracle.
The parent owns source hashes, process limits, clock, parsing and publication.
No candidate pytest configuration, conftest, install hook or plugin is loaded.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time

from boundary import quiesce, strict_json
from execute import CONTEXT_ENV, THREADS, digest

SOURCE_COMMIT = "f3ef4546ddb9eae8af8bd672fc5228693bec32fc"
EXPECTED_COUNT = 59
SELECTION = "(not_equal or _ne or does_not_mutate) and not numba"
PROTECTED_FILES = {
    "tests/functions/test_conditional_join.py":
        "bbda45a4980bcf2184ba4569ad724c2c686855993033fc8598c2e8bc323790e7",
    "janitor/testing_utils/strategies.py":
        "4bcce0111654c2900d39208825277babe6b260846ec879871617dbae39110bc9",
}
# Collected from the pinned reference test file with the selection above (numba is not installed, so its
# variants are excluded by name). The first Linux collection must corroborate these exact 59 identities.
EXPECTED_NODEIDS = tuple(sorted(
    "test_conditional_join.py::" + name for name in (
        "test_check_aggfunc_ne",
        "test_conditional_join_does_not_mutate_inputs",
        "test_conditions_eq_and_gt_ne",
        "test_conditions_eq_and_lt_ne",
        "test_dual_conditions_eq_and_ne",
        "test_dual_conditions_ne_and_eq",
        "test_dual_ne",
        "test_dual_ne_dates",
        "test_dual_ne_extension",
        "test_equi_ge_ge_ne_agg",
        "test_equi_ge_ge_ne_agg_rev",
        "test_equi_ge_ne_agg",
        "test_equi_ge_ne_agg_rev",
        "test_equi_le_ge_ge_ne_agg",
        "test_equi_le_ge_ge_ne_agg_rev",
        "test_equi_le_ge_ne_agg",
        "test_equi_le_ge_ne_agg_rev",
        "test_equi_le_le_ne_agg",
        "test_equi_le_le_ne_agg_rev",
        "test_equi_le_ne_agg",
        "test_equi_le_ne_agg_rev",
        "test_equi_ne_agg",
        "test_equi_ne_agg_rev",
        "test_ge_le_ne_extension_array",
        "test_ge_lt_ne_extension",
        "test_ge_lt_ne_extension_variant",
        "test_gt_lt_ne_conditions",
        "test_gt_lt_ne_conditions_regions",
        "test_gt_lt_ne_start",
        "test_gt_ne_agg",
        "test_gt_ne_agg_rev",
        "test_gt_ne_conditions",
        "test_le_ne_conditions",
        "test_lt_ne_agg",
        "test_lt_ne_agg_rev",
        "test_multiple_ne_dates",
        "test_multiple_range_ne_agg",
        "test_multiple_range_ne_agg_rev",
        "test_single_condition_not_equal_datetime",
        "test_single_condition_not_equal_floats_only",
        "test_single_condition_not_equal_ints",
        "test_single_condition_not_equal_keep_one[all-null-first]",
        "test_single_condition_not_equal_keep_one[all-null-last]",
        "test_single_condition_not_equal_keep_one[datetimes-first]",
        "test_single_condition_not_equal_keep_one[datetimes-last]",
        "test_single_condition_not_equal_keep_one[duplicates-first]",
        "test_single_condition_not_equal_keep_one[duplicates-last]",
        "test_single_condition_not_equal_keep_one[empty-left-first]",
        "test_single_condition_not_equal_keep_one[empty-left-last]",
        "test_single_condition_not_equal_keep_one[empty-right-first]",
        "test_single_condition_not_equal_keep_one[empty-right-last]",
        "test_single_condition_not_equal_keep_one[float-nan-first]",
        "test_single_condition_not_equal_keep_one[float-nan-last]",
        "test_single_condition_not_equal_keep_one[nullable-integers-first]",
        "test_single_condition_not_equal_keep_one[nullable-integers-last]",
        "test_single_condition_not_equal_keep_one[one-distinct-value-first]",
        "test_single_condition_not_equal_keep_one[one-distinct-value-last]",
        "test_single_condition_not_equal_keep_one_preserves_output_order[first-right_positions0]",
        "test_single_condition_not_equal_keep_one_preserves_output_order[last-right_positions1]",
    )
))


class NativeSourceError(ValueError):
    """A pinned verifier input is missing or differs from the declared bytes."""


def selection_manifest(upstream):
    """Check the protected REFERENCE inputs and return a path-independent pin.

    The baseline test file lacks the PR-added keep-one and output-order cases and is
    not the correct input. Both role snapshots run these same 59 reference-source tests.
    """
    upstream = Path(upstream)
    for relative, expected in PROTECTED_FILES.items():
        path = upstream / relative
        if (not path.is_file() or path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents)
                or digest(path) != expected):
            raise NativeSourceError(f"protected native input mismatch: {relative}")
    manifest = {
        "schema_version": 1, "mode": "protected_upstream",
        "source_commit": SOURCE_COMMIT, "selection": SELECTION,
        "expected_count": EXPECTED_COUNT, "nodeids": list(EXPECTED_NODEIDS),
        "files": dict(PROTECTED_FILES),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {**manifest, "sha256": hashlib.sha256(encoded).hexdigest()}


def pytest_arguments(driver):
    """Return a fixed selection with all candidate discovery routes disabled."""
    driver = Path(driver)
    return [
        str(driver / "test_conditional_join.py"), "-q", "-k", SELECTION,
        "-c", str(driver / "pytest.ini"), f"--rootdir={driver}",
        "--noconftest", "--import-mode=importlib", "-p", "no:cacheprovider",
        "-o", "addopts=", "--color=no", "--tb=short", "--maxfail=1",
    ]


def validate_summary(value):
    """Return None only for all expected tests passing all three pytest phases."""
    required = {"schema_version", "selected", "selected_count", "deselected_count",
                "collection_errors", "exit_code", "reports", "duplicate_reports"}
    if not isinstance(value, dict) or set(value) != required:
        return "native summary schema mismatch"
    for key in ("schema_version", "selected_count", "deselected_count",
                "collection_errors", "exit_code"):
        if type(value[key]) is not int or value[key] < 0:
            return f"native {key} must be a nonnegative integer"
    if value["schema_version"] != 1:
        return "native summary version mismatch"
    selected = value["selected"]
    if (not isinstance(selected, list) or len(selected) != EXPECTED_COUNT
            or value["selected_count"] != EXPECTED_COUNT
            or not all(isinstance(item, str) and item for item in selected)
            or len(set(selected)) != EXPECTED_COUNT
            or set(selected) != set(EXPECTED_NODEIDS)):
        return "native selected test count/identity mismatch"
    if value["collection_errors"] or value["exit_code"]:
        return "native collection or pytest exit failure"
    if value["duplicate_reports"] != []:
        return "native duplicate test-phase reports"
    reports = value["reports"]
    if not isinstance(reports, dict) or set(reports) != set(selected):
        return "native missing or extra reports"
    complete = {phase: "passed" for phase in ("setup", "call", "teardown")}
    if any(phases != complete for phases in reports.values()):
        return "native failed, skipped, or incomplete test phase"
    return None


def validate_limits(limits, timeout):
    """Reject invalid controls before starting any child."""
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0):
        raise ValueError("native timeout must be positive and finite")
    for key in ("max_output_bytes", "address_space_bytes"):
        if type(limits.get(key)) is not int or limits[key] <= 0:
            raise ValueError(f"native {key} must be a positive integer")


def native_environment(writable):
    """Build an allowlisted environment without inherited pytest/Python options."""
    writable = Path(writable)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(writable),
           "TMPDIR": str(writable), "LANG": "C.UTF-8", "PYTHONHASHSEED": "0",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
           "HYPOTHESIS_STORAGE_DIRECTORY": str(writable / "hypothesis"), **THREADS}
    env.update({name: os.environ[name] for name in CONTEXT_ENV if name in os.environ})
    return env


def termination_outcome(exit_code, timed_out):
    """Do not infer a submission timeout from an unexplained external kill."""
    if timed_out:
        return "failed", "native worker exceeded its observed deadline"
    if exit_code == -signal.SIGKILL:
        return "verifier_invalid", "native worker ended by unattributed SIGKILL"
    return None


WORKER_CODE = r'''
"""Staged public native assertions; no private oracle or reward authority."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

# Resolve trusted installed dependencies before adding candidate source.
import pytest
import numpy
import pandas
import hypothesis
from hypothesis import settings

source, driver, arguments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
settings.register_profile("afterquery_native", database=None, derandomize=True)
settings.load_profile("afterquery_native")

class Reports:
    def __init__(self):
        self.selected = []
        self.deselected_count = 0
        self.collection_errors = 0
        self.reports = {}
        self.duplicate_reports = []

    def pytest_collection_finish(self, session):
        self.selected = [item.nodeid for item in session.items]

    def pytest_deselected(self, items):
        self.deselected_count += len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        phases = self.reports.setdefault(report.nodeid, {})
        if report.when in phases:
            self.duplicate_reports.append([report.nodeid, report.when])
        phases[report.when] = report.outcome

collector = Reports()
with contextlib.redirect_stdout(sys.stderr):
    sys.path.insert(0, source)
    import janitor
    # The upstream generator is an assertion input, not editable production code.
    package = types.ModuleType("janitor.testing_utils")
    package.__path__ = []
    sys.modules["janitor.testing_utils"] = package
    janitor.testing_utils = package
    spec = importlib.util.spec_from_file_location(
        "janitor.testing_utils.strategies", driver / "strategies.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    package.strategies = module
    exit_code = int(pytest.main(arguments, plugins=[collector]))

print(json.dumps({
    "schema_version": 1, "selected": collector.selected,
    "selected_count": len(collector.selected),
    "deselected_count": collector.deselected_count,
    "collection_errors": collector.collection_errors,
    "exit_code": exit_code, "reports": collector.reports,
    "duplicate_reports": collector.duplicate_reports,
}, sort_keys=True, allow_nan=False))
sys.exit(exit_code)
'''


def _stage(upstream, driver, manifest):
    """Copy exactly pinned public assertions into a root-owned read-only driver."""
    driver.mkdir(mode=0o755)
    for relative, expected in manifest["files"].items():
        data = (Path(upstream) / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise NativeSourceError("protected native input changed during staging")
        target = driver / Path(relative).name
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n    turtle: upstream slow property test\n"
        "    functions: upstream DataFrame function test\n"
    )
    for path in driver.iterdir():
        path.chmod(0o444)
    driver.chmod(0o555)


def run_native(python, source, upstream, scratch, role, limits, timeout):
    """Run the pinned selection on a role's already immutable source snapshot.

    Caller owns the cumulative deadline and accounts returned wall_seconds; this
    function enforces the passed remaining timeout, process limits and cleanup.
    It requires root in Linux, like execute.run_worker. Never install candidate
    code or call it in the parent. Failures of a baseline role invalidate the
    enclosing comparison; that decision belongs to the caller.
    """
    record = {
        "mode": "protected_upstream", "outcome": "verifier_invalid",
        "reason": None, "role": role, "expected_count": EXPECTED_COUNT,
        "collected_count": None, "passed_count": 0, "wall_seconds": 0.0,
        "cpu_seconds": 0.0, "exit_code": None, "timeout": False,
        "timeout_seconds_effective": timeout, "protected_inputs": None,
        "stdout_path": None, "stderr_path": None,
        "stdout_sha256": None, "stderr_sha256": None,
        "uid_quiescence": None,
        "claim_limit": "supplementary native regression, not adversarial proof",
    }
    try:
        validate_limits(limits, timeout)
        if role not in ("candidate", "baseline"):
            raise ValueError("native role must be candidate or baseline")
        if sys.platform != "linux" or os.geteuid() != 0:
            raise ValueError("native gate requires root-owned Linux isolation")
        source = Path(source)
        if source.is_symlink() or not source.is_dir():
            raise ValueError("native source must be the real snapshot directory")
        source = source.resolve(strict=True)
        manifest = selection_manifest(upstream)
        record["protected_inputs"] = manifest
        uid = 10001 if role == "candidate" else 10002
        record["uid"] = uid
        before = quiesce((uid,))
        record["pre_uid_quiescence"] = before
        if before.get("quiescent") is not True:
            raise ValueError("native UID was not quiescent before start")
        scratch = Path(scratch).absolute()
        scratch.mkdir(mode=0o711)
        scratch.chmod(0o711)  # Explicit public traversal despite the private entrypoint umask.
        driver, writable = scratch / "driver", scratch / "writable"
        _stage(upstream, driver, manifest)
        writable.mkdir(mode=0o700)
        os.chown(writable, uid, uid)
    except (OSError, ValueError) as exc:
        record["reason"] = str(exc)
        return record

    command = [str(python), "-I", "-B", str(driver / "bootstrap.py"),
               str(source), str(driver), json.dumps(pytest_arguments(driver))]
    env = native_environment(writable)

    def demote():
        os.umask(0o077)
        if hasattr(os, "sched_getaffinity"):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        cpu = max(1, math.ceil(timeout))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE,
                           (limits["max_output_bytes"], limits["max_output_bytes"]))
        resource.setrlimit(resource.RLIMIT_AS,
                           (limits["address_space_bytes"], limits["address_space_bytes"]))
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))

    stdout_path, stderr_path = scratch / "stdout.json", scratch / "stderr.log"
    record.update(stdout_path=str(stdout_path), stderr_path=str(stderr_path))
    start = time.monotonic()
    proc = None
    try:
        with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
            proc = subprocess.Popen(command, cwd=writable, env=env, stdout=out,
                                    stderr=err, preexec_fn=demote, start_new_session=True)
            while True:
                waited, status, usage = os.wait4(proc.pid, os.WNOHANG)
                if waited:
                    break
                if time.monotonic() - start >= timeout:
                    record["timeout"] = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(proc.pid, 0)
                    break
                time.sleep(0.002)
            proc.returncode = os.waitstatus_to_exitcode(status)
            record.update(exit_code=proc.returncode,
                          cpu_seconds=usage.ru_utime + usage.ru_stime)
    except (OSError, subprocess.SubprocessError) as exc:
        record["reason"] = f"native worker launch/wait error: {exc}"
    finally:
        record["wall_seconds"] = time.monotonic() - start
        residual = False
        if proc is not None:
            try:
                os.killpg(proc.pid, 0)
                residual = True
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if proc.returncode is None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    record["reason"] = "native process could not be reaped after cleanup"
        quiet = quiesce((uid,))
        record["uid_quiescence"] = quiet
        record["surviving_process"] = residual or bool(quiet["initial_pids"])

    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        if path.is_file():
            record[f"{label}_sha256"] = digest(path)
    if record["reason"]:
        return record
    if quiet.get("quiescent") is not True:
        record["reason"] = "native worker UID did not quiesce"
        return record
    termination = termination_outcome(record["exit_code"], record["timeout"])
    if termination is not None:
        record["outcome"], record["reason"] = termination
        return record
    record["outcome"] = "failed"
    if record["surviving_process"]:
        record["reason"] = "native worker left a surviving process"
        return record
    try:
        info = stdout_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_size > limits["max_output_bytes"]):
            raise ValueError("native stdout is not a bounded root-owned regular stream")
        summary = strict_json(stdout_path.read_text())
        record["native_summary"] = summary
        reason = validate_summary(summary)
        if isinstance(summary, dict):
            count = summary.get("selected_count")
            if type(count) is int and count >= 0:
                record["collected_count"] = count
            reports = summary.get("reports")
            if isinstance(reports, dict):
                record["passed_count"] = sum(
                    isinstance(phases, dict) and phases.get("call") == "passed"
                    for phases in reports.values())
        if reason:
            raise ValueError(reason)
        if record["exit_code"] != 0:
            raise ValueError("native process exit disagrees with passing summary")
    except (OSError, UnicodeError, ValueError) as exc:
        record["reason"] = str(exc)
        return record
    record.update(outcome="passed", reason=None)
    return record
