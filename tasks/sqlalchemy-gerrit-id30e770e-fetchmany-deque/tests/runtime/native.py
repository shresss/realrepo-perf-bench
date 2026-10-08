"""Bounded, protected upstream regression selection. TEMPLATE: fill every Adapter note.

Derived from the Harbor-proven pyjanitor1644 adapter; only marked blocks differ.

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

# ---- Adapter note: every value in this block is task-specific. Fill from the REFERENCE
# commit's test files; both baseline and candidate run this same protected selection.
SOURCE_COMMIT = "7782e2b3ad5a6a8c860f689f345a00ae47db6c7f"
PROTECTED_FILES = {'setup.cfg': 'cae1a4b680eaa329b84d04aba1d14831aaef30d9a680ab94821618b0c7433d69', 'test/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'test/requirements.py': 'd1abae5d2adfe4cf5346d51a6e26236fe67d75b7c279e7aee21f35cb647e99eb', 'test/conftest.py': '507de24b2b55d5a9eafd4f5d1c39435840ee1e6b4aae67effe2ce95f8fd10245', 'test/profiles.txt': '73ade00fcd1f04eec06961f70883a1364b2f5e1320db5c8b663082ef685c86f6', 'test/sql/test_resultset.py': '348d72e5af45aef7a682a965b252d05cedefad94c345c6ba184fe8fb62cd1c14', 'test/base/test_result.py': 'b31cbc33cf344fc414ffee3c5c861f16776cfe22c8ff5b0ba705cf51a091e0e5', 'lib/sqlalchemy/testing/pickleable.py': '53d988aa4fb36b1abd5dfcbb1c4acfed4aca813a2ff80dd016785987e3623a32', 'lib/sqlalchemy/testing/exclusions.py': '4fc074d619a6f1656cf8429c50e411cda6da84fa9b95625f3a2762e9b1c9e860', 'lib/sqlalchemy/testing/config.py': '43fdbbd10c0a23560f35e09a26903d2e8232f391642a8ad878165c0420aa4a64', 'lib/sqlalchemy/testing/engines.py': '2db5e2b71113f3c54539b31b3e44c1f415eff97bac608b11cdd1af3640034dce', 'lib/sqlalchemy/testing/util.py': '045892a770845fde43afebefe25ffb651bb9be3662f618e39e9f8928d7ee4b91', 'lib/sqlalchemy/testing/warnings.py': '7c9f90254636cd8d8f3f16492aff6679d5be04a29b08d6c0e0db3f5776301573', 'lib/sqlalchemy/testing/asyncio.py': 'caaae823b0827c1cf6bce5d118809c8801da74869265f694f890baa6095223fe', 'lib/sqlalchemy/testing/__init__.py': '56cac41eb391a401799fb55f978dd842000187a10fd71071fe01f1b3ba525de1', 'lib/sqlalchemy/testing/assertions.py': '80bd2b03b0826496dc560bd638f57dd6d4d94d1c10735fd36b4fb29019fcdc4c', 'lib/sqlalchemy/testing/assertsql.py': '220406ee5f7859a8913fc9d36e2949875647665d76e60ec63eaf92e6499064dd', 'lib/sqlalchemy/testing/provision.py': 'cc494ddd6181a6af5a246d2913421a60ab396d5db3187749f7dcf3e9e21ac78c', 'lib/sqlalchemy/testing/requirements.py': 'f5fdfcc0ec659cbcfb374832bce5058de0c79a6dc17cbe2777bec8860193fd53', 'lib/sqlalchemy/testing/entities.py': '2298457a03ca6df7f7527e3b8d8e9b8bbfcc417cbaaa4c7fe748d7dad1d9251e', 'lib/sqlalchemy/testing/profiling.py': '3dbb8f85115b6ae16295438d798ded57f63fe650640fb8826bc555c87d9293d6', 'lib/sqlalchemy/testing/schema.py': '96be06906ac6c1a81a1ccb921b359dce431a8f71e74bb7607cb2d67f1b7fffe5', 'lib/sqlalchemy/testing/plugin/bootstrap.py': 'a1849c31b116e290a75a53c402ad629ec16bb825c541e115070a3ffe2e0c7295', 'lib/sqlalchemy/testing/plugin/plugin_base.py': '06037358d1268292b80b08726e54102a71feec50ca562fd4ba5e6fc3c7c58c15', 'lib/sqlalchemy/testing/plugin/__init__.py': 'efd17ef81218fcd4c1cd54489491a0018e4b349277703d7d5efac0a385f45bd0', 'lib/sqlalchemy/testing/plugin/pytestplugin.py': 'c024371de13073f53717be6a29f6d0ad3c90d00ea4fd43b7d63087e40033f2cf', 'lib/sqlalchemy/testing/fixtures/orm.py': 'f0415b9da05b5d7fc17f815c0b30546801e0c95a6c2c60475f5e9218ba84dc58', 'lib/sqlalchemy/testing/fixtures/__init__.py': '74c0a5ac8a31aa560816993689ae1166991b7f1b12ff71018a0afd42c3c9eba8', 'lib/sqlalchemy/testing/fixtures/mypy.py': '81dc62c0d148cc394d19239dbccde06f00dc795082f6df2833990a6f0ca11819', 'lib/sqlalchemy/testing/fixtures/sql.py': '4c4e6ad8148e73f56ad533da2e78f517d640fd88901e5ab2bd4b4621df5b1abd', 'lib/sqlalchemy/testing/fixtures/base.py': 'f6bfc9da4b224f30a5a54c56d137332021eb591ecdcbc3d5f08b01cfa4ec1852', 'lib/sqlalchemy/testing/suite/test_sequence.py': 'eba6c2a32e31a3df46052697e87c5bf3c7e800d03290b191cf560429bbe97ee0', 'lib/sqlalchemy/testing/suite/test_results.py': '350db79bc14355dd2e6fbe758cde0fb301a80219399ebaaf8c7be96142d95e77', 'lib/sqlalchemy/testing/suite/test_insert.py': 'f5ace27e3ebe3820fbb3c87fb403b5b8fc35d3489b42ff18a0a73f540de19f77', 'lib/sqlalchemy/testing/suite/test_select.py': '16f3056105bd209a43586619889938ea2b3a62bb6675282105d4e36421bc4f46', 'lib/sqlalchemy/testing/suite/test_deprecations.py': '05c27165372362a78e0043551250a0de156f53a7e41845b728604c7e75bc6e78', 'lib/sqlalchemy/testing/suite/test_ddl.py': 'd4da647f40bfe14371a61b610068c6d3bf27d2f3c48274881e90eee4c7e89314', 'lib/sqlalchemy/testing/suite/test_dialect.py': '107e194166e719db639b1e5a999b53ca1626ae45c90af5b5490a0b6a1a04eee9', 'lib/sqlalchemy/testing/suite/__init__.py': '6390d1346d18975bb7ca9b7dcd517467db2e3d97ae3bf51018b97ec1182f4e35', 'lib/sqlalchemy/testing/suite/test_update_delete.py': 'c9388cdae9e77ce2bdacaf1992a7934d4fcc913f91b0a14b99d6258a78997c06', 'lib/sqlalchemy/testing/suite/test_reflection.py': 'b4949b2458397f0d2c494bf723f14f9a137bad659e26dab7632c66ca55895253', 'lib/sqlalchemy/testing/suite/test_rowcount.py': 'dca0d3951823a50d4e55fa7fff572ff07beae02b032b39ab84943f588256a098', 'lib/sqlalchemy/testing/suite/test_cte.py': 'eb3042dd6d8ec17d57b3e1de77372170a3764bb11a2cd92092f57f25267f3ead', 'lib/sqlalchemy/testing/suite/test_types.py': 'ac59933a0e97b8c721f4bdbe5ed85f2c94424d3c2965b31facdb2cda0d3d8267', 'lib/sqlalchemy/testing/suite/test_unicode_ddl.py': '737fde2312f2391b923a13433f48d62b13f251fdd2c0c16975a971b6abb0aa53'}
TEST_FILES = ("test/sql/test_resultset.py", "test/base/test_result.py")
SELECTION = "fetchmany or partition or buffer"
EXPECTED_NODEIDS = ('test/base/test_result.py::OnlyScalarsTest::test_scalar_mode_scalars_fetchmany', 'test/base/test_result.py::OnlyScalarsTest::test_scalar_mode_unique_scalars_fetchmany', 'test/base/test_result.py::ResultTest::test_partition', 'test/base/test_result.py::ResultTest::test_partition_unique_yield_per', 'test/base/test_result.py::ResultTest::test_partition_yield_per', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_basic_buffered_column_result_proxy', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_basic_buffered_row_result_proxy', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_basic_fully_buffered_result_proxy', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchall-False]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchall-True]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchmany-False]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchmany-True]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchone-False]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetch_auto_soft_close[fetchone-True]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetchmany_fixed', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetchmany_yield_per', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_fetchmany_yield_per_all', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_row_close_error_during_fetchone', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_row_growth[gt 1000]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_row_growth[gt 1500]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_row_growth[lt 1000]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_buffered_row_growth[no option]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchall-BufferedRowCursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchmany-BufferedRowCursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchmany-CursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchmany_w_num-BufferedRowCursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchmany_w_num-CursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_handle_error_in_fetch[fetchone-BufferedRowCursorFetchStrategy]', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_resultprocessor_buffered_row', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_resultprocessor_buffered_row_cached', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_resultprocessor_fully_buffered', 'test/sql/test_resultset.py::AlternateCursorResultTest::test_resultprocessor_fully_buffered_cached', 'test/sql/test_resultset.py::CursorResultTest_sqlite+pysqlite::test_fetchmany', 'test/sql/test_resultset.py::CursorResultTest_sqlite+pysqlite::test_fetchmany_arraysize_default', 'test/sql/test_resultset.py::CursorResultTest_sqlite+pysqlite::test_fetchmany_arraysize_set', 'test/sql/test_resultset.py::GenerativeResultTest_sqlite+pysqlite::test_partitions')
EXPECTED_COUNT = len(EXPECTED_NODEIDS)
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
        *(str(driver / p) for p in TEST_FILES), "-q", "-k", SELECTION,
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
import re

def canonical_nodeid(value):
    # Upstream generates the SQLite library version in four class IDs.
    # Normalize only that nonsemantic version suffix; preserve every logical test ID.
    return re.sub(r"_sqlite\+pysqlite_\d+(?:_\d+)*::", "_sqlite+pysqlite::", value)

# Resolve trusted installed dependencies before adding candidate source.
# Adapter note: import heavy third-party deps here so they resolve from site-packages.
import pytest

source, driver, arguments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
# Adapter note: if hypothesis is used, keep it deterministic:
# from hypothesis import settings
# settings.register_profile("afterquery_native", database=None, derandomize=True)
# settings.load_profile("afterquery_native")

class Reports:
    def __init__(self):
        self.selected = []
        self.deselected_count = 0
        self.collection_errors = 0
        self.reports = {}
        self.duplicate_reports = []

    def pytest_collection_finish(self, session):
        self.selected = [canonical_nodeid(item.nodeid) for item in session.items]

    def pytest_deselected(self, items):
        self.deselected_count += len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        nodeid = canonical_nodeid(report.nodeid)
        phases = self.reports.setdefault(nodeid, {})
        if report.when in phases:
            self.duplicate_reports.append([nodeid, report.when])
        phases[report.when] = report.outcome

collector = Reports()
with contextlib.redirect_stdout(sys.stderr):
    sys.path.insert(0, source)
    # Adapter note: import the package under test here (resolves from `source`).
    # If tests import repo helper modules (e.g. tests/helpers.py), load them from
    # `driver` with importlib like the pyjanitor adapter did for strategies.py.
    # If they need conftest fixtures, load that conftest from `driver` and pass it
    # in plugins=[collector, conftest_module]; --noconftest stays on.
    sys.path.insert(0, str(Path(source) / "lib"))
    import sqlalchemy
    # Load only the pinned upstream test-support package from the protected driver.
    sqlalchemy.__path__.insert(0, str(driver / "lib" / "sqlalchemy"))
    sys.path.insert(0, str(driver))
    spec = importlib.util.spec_from_file_location("protected_sqla_conftest", driver / "test" / "conftest.py")
    protected_conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protected_conftest)
    exit_code = int(pytest.main(arguments, plugins=[collector, protected_conftest]))

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
        target = driver / relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n"  # Adapter note: register upstream markers if any
    )
    for path in driver.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
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
