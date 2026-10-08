"""Bounded, protected upstream regression selection for requests-cache PR 573.

Derived from the Harbor-proven pyjanitor1644 adapter; only the marked task block,
the conftest/package loading in WORKER_CODE and the sample_data stub in _stage differ.

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

# ---- task-specific block (requests-cache 573). Reference-commit test files; both
# baseline and candidate run this same protected selection.
SOURCE_COMMIT = "2bd683658e17602a826a26b864a399b68181ee33"
# Repo-relative paths of protected assertion inputs -> sha256 of the reference bytes.
# _stage() FLATTENS them into one driver dir by basename: basenames must be unique.
PROTECTED_FILES = {
    "tests/unit/test_session.py":
        "0fd793305f2acb84ec0b51693a128ce5f4ac81a73d6b92e00535de106ffceae3",
    "tests/conftest.py":
        "bb89aaec6c6193473d610a858346a79302053043b5bd5d783764536727827101",
    "tests/integration/test_sqlite.py":
        "56d2da49f738718900f88c6405fb6fc01b9fb0b32ac6f0bb50015e3d8cb102d8",
    "tests/integration/base_storage_test.py":
        "08711942add8c039ba1c8181f373a3465148fc64f19a8242195b551bad622373",
    "tests/integration/base_cache_test.py":
        "de2b8c7ec8b3d2e6dbdc08b803de38a0e953b8d82c47eb9aae6529bf09148254",
}
TEST_FILES = ("test_session.py", "test_sqlite.py")  # basenames inside the driver dir
# Deterministic subset: upstream sleep(1)/expire_after=1 tests are excluded (measured
# flaky about 1 in 4 runs on baseline in Linux), as are PR-added sorted() tests (absent
# on baseline), the thread-spawning bulk_commit noop test (workers run with NPROC=1) and
# test_use_temp (asserts the cwd is outside gettempdir(); the verifier cwd is under /tmp).
SELECTION = (
    "(test_session and (expire_after_alias or expire_immediately or "
    "remove_expired_responses__error or extend_expiration or shorten_expiration or "
    "disable_expiration)) or ((TestSQLiteDict or TestSQLitePickleDict) and not sorted "
    "and not noop and not use_temp)"
)
EXPECTED_NODEIDS = tuple(sorted((
    "test_session.py::test_expire_after_alias",
    "test_session.py::test_expire_immediately",
    "test_session.py::test_remove_expired_responses__error",
    "test_session.py::test_remove_expired_responses__extend_expiration",
    "test_session.py::test_remove_expired_responses__shorten_expiration",
    "test_session.py::test_request_expire_after__disable_expiration",
    "test_sqlite.py::TestSQLiteDict::test_basic_methods",
    "test_sqlite.py::TestSQLiteDict::test_iterable_methods",
    "test_sqlite.py::TestSQLiteDict::test_del",
    "test_sqlite.py::TestSQLiteDict::test_bulk_delete",
    "test_sqlite.py::TestSQLiteDict::test_keyerrors",
    "test_sqlite.py::TestSQLiteDict::test_picklable_dict",
    "test_sqlite.py::TestSQLiteDict::test_clear_and_work_again",
    "test_sqlite.py::TestSQLiteDict::test_same_settings",
    "test_sqlite.py::TestSQLiteDict::test_str",
    "test_sqlite.py::TestSQLiteDict::test_connection_kwargs",
    "test_sqlite.py::TestSQLiteDict::test_use_cache_dir",
    "test_sqlite.py::TestSQLiteDict::test_use_memory",
    "test_sqlite.py::TestSQLiteDict::test_use_memory__uri",
    "test_sqlite.py::TestSQLiteDict::test_non_dir_parent_exists",
    "test_sqlite.py::TestSQLiteDict::test_bulk_commit",
    "test_sqlite.py::TestSQLiteDict::test_bulk_delete__chunked",
    "test_sqlite.py::TestSQLiteDict::test_switch_commit",
    "test_sqlite.py::TestSQLiteDict::test_pragma[kwargs0]",
    "test_sqlite.py::TestSQLiteDict::test_pragma[kwargs1]",
    "test_sqlite.py::TestSQLitePickleDict::test_basic_methods",
    "test_sqlite.py::TestSQLitePickleDict::test_iterable_methods",
    "test_sqlite.py::TestSQLitePickleDict::test_del",
    "test_sqlite.py::TestSQLitePickleDict::test_bulk_delete",
    "test_sqlite.py::TestSQLitePickleDict::test_keyerrors",
    "test_sqlite.py::TestSQLitePickleDict::test_picklable_dict",
    "test_sqlite.py::TestSQLitePickleDict::test_clear_and_work_again",
    "test_sqlite.py::TestSQLitePickleDict::test_same_settings",
    "test_sqlite.py::TestSQLitePickleDict::test_str",
    "test_sqlite.py::TestSQLitePickleDict::test_connection_kwargs",
    "test_sqlite.py::TestSQLitePickleDict::test_use_cache_dir",
    "test_sqlite.py::TestSQLitePickleDict::test_use_memory",
    "test_sqlite.py::TestSQLitePickleDict::test_use_memory__uri",
    "test_sqlite.py::TestSQLitePickleDict::test_non_dir_parent_exists",
    "test_sqlite.py::TestSQLitePickleDict::test_bulk_commit",
    "test_sqlite.py::TestSQLitePickleDict::test_bulk_delete__chunked",
    "test_sqlite.py::TestSQLitePickleDict::test_switch_commit",
    "test_sqlite.py::TestSQLitePickleDict::test_pragma[kwargs0]",
    "test_sqlite.py::TestSQLitePickleDict::test_pragma[kwargs1]",
)))
EXPECTED_COUNT = len(EXPECTED_NODEIDS)  # must equal the Linux collection count exactly (44)
# ---- end task-specific block


class NativeSourceError(ValueError):
    """A pinned verifier input is missing or differs from the declared bytes."""


def selection_manifest(upstream):
    """Check the protected REFERENCE inputs and return a path-independent pin.

    Both role snapshots run these same reference-source tests.
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
        *[str(driver / name) for name in TEST_FILES], "-q", "-k", SELECTION,
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
import requests
import requests_mock
import rich.logging
import timeout_decorator
import cattrs
import attr
import url_normalize
import platformdirs

source, driver, arguments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])

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
    import requests_cache  # noqa: F401  (resolves from the role snapshot)
    # The pinned upstream conftest is an assertion input (fixtures + constants that
    # test_session.py imports as tests.conftest), loaded from the root-owned driver.
    package = types.ModuleType("tests")
    package.__path__ = []
    sys.modules["tests"] = package
    spec = importlib.util.spec_from_file_location("tests.conftest", driver / "conftest.py")
    conftest = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = conftest
    spec.loader.exec_module(conftest)
    package.conftest = conftest
    integration = types.ModuleType("tests.integration")
    integration.__path__ = []
    sys.modules["tests.integration"] = integration
    package.integration = integration
    for helper in ("base_storage_test", "base_cache_test"):
        spec = importlib.util.spec_from_file_location(
            "tests.integration." + helper, driver / (helper + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        setattr(integration, helper, module)
    exit_code = int(pytest.main(arguments, plugins=[collector, conftest]))

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
    # conftest.py lists <driver parent>/tests/sample_data at import; give it an empty,
    # root-owned, read-only stand-in (the selected tests never read sample databases).
    sample = driver.parent / "tests" / "sample_data"
    sample.mkdir(parents=True, mode=0o755)
    sample.chmod(0o555)
    sample.parent.chmod(0o555)
    for relative, expected in manifest["files"].items():
        data = (Path(upstream) / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise NativeSourceError("protected native input changed during staging")
        target = driver / Path(relative).name
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n"  # upstream selection uses only parametrize
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
