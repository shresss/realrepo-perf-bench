"""Bounded, protected upstream regression selection for SQLGlot PR 3901 (parser joins/APPLY).

This supplements the parent's independent oracle. Unittest and candidate Python
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

SOURCE_COMMIT = "bea3c08e46a020d8545b702c77f0db18c99f1c55"
# Every TestParser method except test_parse_nested (wall-clock asserts; never finishes on the base),
# every TestTSQL method and every TestTranspile method, from the reference commit.
METHODS = (
    "tests.test_parser:TestParser.test_parse_empty",
    "tests.test_parser:TestParser.test_parse_into",
    "tests.test_parser:TestParser.test_parse_into_error",
    "tests.test_parser:TestParser.test_parse_into_errors",
    "tests.test_parser:TestParser.test_column",
    "tests.test_parser:TestParser.test_tuple",
    "tests.test_parser:TestParser.test_structs",
    "tests.test_parser:TestParser.test_float",
    "tests.test_parser:TestParser.test_unnest",
    "tests.test_parser:TestParser.test_unnest_projection",
    "tests.test_parser:TestParser.test_unary_plus",
    "tests.test_parser:TestParser.test_table",
    "tests.test_parser:TestParser.test_union",
    "tests.test_parser:TestParser.test_select",
    "tests.test_parser:TestParser.test_command",
    "tests.test_parser:TestParser.test_lambda_struct",
    "tests.test_parser:TestParser.test_transactions",
    "tests.test_parser:TestParser.test_identify",
    "tests.test_parser:TestParser.test_multi",
    "tests.test_parser:TestParser.test_expression",
    "tests.test_parser:TestParser.test_parse_errors",
    "tests.test_parser:TestParser.test_space",
    "tests.test_parser:TestParser.test_missing_by",
    "tests.test_parser:TestParser.test_parameter",
    "tests.test_parser:TestParser.test_var",
    "tests.test_parser:TestParser.test_comments_select",
    "tests.test_parser:TestParser.test_comments_select_cte",
    "tests.test_parser:TestParser.test_comments_insert",
    "tests.test_parser:TestParser.test_comments_insert_cte",
    "tests.test_parser:TestParser.test_comments_update",
    "tests.test_parser:TestParser.test_comments_update_cte",
    "tests.test_parser:TestParser.test_comments_delete",
    "tests.test_parser:TestParser.test_comments_delete_cte",
    "tests.test_parser:TestParser.test_type_literals",
    "tests.test_parser:TestParser.test_set_expression",
    "tests.test_parser:TestParser.test_pretty_config_override",
    "tests.test_parser:TestParser.test_comment_error_n",
    "tests.test_parser:TestParser.test_comment_error_r",
    "tests.test_parser:TestParser.test_create_table_error",
    "tests.test_parser:TestParser.test_pivot_columns",
    "tests.test_parser:TestParser.test_parse_properties",
    "tests.test_parser:TestParser.test_parse_floats",
    "tests.test_parser:TestParser.test_parse_terse_coalesce",
    "tests.test_parser:TestParser.test_parse_intervals",
    "tests.test_parser:TestParser.test_parse_concat_ws",
    "tests.test_parser:TestParser.test_parse_drop_schema",
    "tests.test_parser:TestParser.test_parse_create_schema",
    "tests.test_parser:TestParser.test_values_as_identifier",
    "tests.test_parser:TestParser.test_alter_set",
    "tests.test_parser:TestParser.test_distinct_from",
    "tests.test_parser:TestParser.test_trailing_comments",
    "tests.test_parser:TestParser.test_parse_prop_eq",
    "tests.test_parser:TestParser.test_collate",
    "tests.dialects.test_tsql:TestTSQL.test_tsql",
    "tests.dialects.test_tsql:TestTSQL.test_option",
    "tests.dialects.test_tsql:TestTSQL.test_types",
    "tests.dialects.test_tsql:TestTSQL.test_types_ints",
    "tests.dialects.test_tsql:TestTSQL.test_types_decimals",
    "tests.dialects.test_tsql:TestTSQL.test_types_string",
    "tests.dialects.test_tsql:TestTSQL.test_types_date",
    "tests.dialects.test_tsql:TestTSQL.test_types_bin",
    "tests.dialects.test_tsql:TestTSQL.test_ddl",
    "tests.dialects.test_tsql:TestTSQL.test_insert_cte",
    "tests.dialects.test_tsql:TestTSQL.test_transaction",
    "tests.dialects.test_tsql:TestTSQL.test_commit",
    "tests.dialects.test_tsql:TestTSQL.test_rollback",
    "tests.dialects.test_tsql:TestTSQL.test_udf",
    "tests.dialects.test_tsql:TestTSQL.test_procedure_keywords",
    "tests.dialects.test_tsql:TestTSQL.test_fullproc",
    "tests.dialects.test_tsql:TestTSQL.test_charindex",
    "tests.dialects.test_tsql:TestTSQL.test_len",
    "tests.dialects.test_tsql:TestTSQL.test_replicate",
    "tests.dialects.test_tsql:TestTSQL.test_isnull",
    "tests.dialects.test_tsql:TestTSQL.test_json",
    "tests.dialects.test_tsql:TestTSQL.test_datefromparts",
    "tests.dialects.test_tsql:TestTSQL.test_datename",
    "tests.dialects.test_tsql:TestTSQL.test_datepart",
    "tests.dialects.test_tsql:TestTSQL.test_convert",
    "tests.dialects.test_tsql:TestTSQL.test_add_date",
    "tests.dialects.test_tsql:TestTSQL.test_date_diff",
    "tests.dialects.test_tsql:TestTSQL.test_lateral_subquery",
    "tests.dialects.test_tsql:TestTSQL.test_lateral_table_valued_function",
    "tests.dialects.test_tsql:TestTSQL.test_top",
    "tests.dialects.test_tsql:TestTSQL.test_format",
    "tests.dialects.test_tsql:TestTSQL.test_string",
    "tests.dialects.test_tsql:TestTSQL.test_eomonth",
    "tests.dialects.test_tsql:TestTSQL.test_identifier_prefixes",
    "tests.dialects.test_tsql:TestTSQL.test_temporal_table",
    "tests.dialects.test_tsql:TestTSQL.test_system_time",
    "tests.dialects.test_tsql:TestTSQL.test_current_user",
    "tests.dialects.test_tsql:TestTSQL.test_hints",
    "tests.dialects.test_tsql:TestTSQL.test_openjson",
    "tests.dialects.test_tsql:TestTSQL.test_set",
    "tests.dialects.test_tsql:TestTSQL.test_qualify_derived_table_outputs",
    "tests.dialects.test_tsql:TestTSQL.test_declare",
    "tests.dialects.test_tsql:TestTSQL.test_scope_resolution_op",
    "tests.test_transpile:TestTranspile.test_weird_chars",
    "tests.test_transpile:TestTranspile.test_alias",
    "tests.test_transpile:TestTranspile.test_unary",
    "tests.test_transpile:TestTranspile.test_paren",
    "tests.test_transpile:TestTranspile.test_some",
    "tests.test_transpile:TestTranspile.test_leading_comma",
    "tests.test_transpile:TestTranspile.test_space",
    "tests.test_transpile:TestTranspile.test_comments",
    "tests.test_transpile:TestTranspile.test_types",
    "tests.test_transpile:TestTranspile.test_not_range",
    "tests.test_transpile:TestTranspile.test_extract",
    "tests.test_transpile:TestTranspile.test_if",
    "tests.test_transpile:TestTranspile.test_with",
    "tests.test_transpile:TestTranspile.test_alter",
    "tests.test_transpile:TestTranspile.test_time",
    "tests.test_transpile:TestTranspile.test_index_offset",
    "tests.test_transpile:TestTranspile.test_identify_lambda",
    "tests.test_transpile:TestTranspile.test_identity",
    "tests.test_transpile:TestTranspile.test_command_identity",
    "tests.test_transpile:TestTranspile.test_normalize_name",
    "tests.test_transpile:TestTranspile.test_partial",
    "tests.test_transpile:TestTranspile.test_pretty",
    "tests.test_transpile:TestTranspile.test_pretty_line_breaks",
    "tests.test_transpile:TestTranspile.test_error_level",
    "tests.test_transpile:TestTranspile.test_unsupported_level",
    "tests.test_transpile:TestTranspile.test_recursion",
)
EXPECTED_COUNT = 122
SELECTION = ",".join(METHODS)
PROTECTED_FILES = {
    "tests/test_parser.py": "8e0f63612faca71522c7a78abfb2fd3d71cff3d32ec8e6664591c10b6649e303",
    "tests/helpers.py": "5d6399d51a4da72eddbc8973f0936e31b7d07adc426ea97a778fa7e7945dc992",
    "tests/dialects/test_tsql.py": "60a6ec21069041a13672fd8b7053c4ee1ef9ab1426497f372d04edeece725db0",
    "tests/dialects/test_dialect.py": "b52eba45574ee2f787e6164489c1e17c73cde6f1c6397c7d9cabde4648a17cf7",
    "tests/test_transpile.py": "75f4612aa2f51acb8e2c3a3c90d1f9f2b96ac0991b58ced94fda84ded640b36d",
    "tests/fixtures/identity.sql": "9b9abaa8e8ec82e13aa8c653fce165e7ae2cbdc3a8c5cdbe67a616f34a21ab0c",
    "tests/fixtures/partial.sql": "c10d3dc1dc1245a277b2e98d5965427830e41401888bb1186d472ceaa0a8d5d8",
    "tests/fixtures/pretty.sql": "0038edb362a779a8a1591470f19d8c9b60b039db5252bfd76f279a04f9ec9bb1",
}
EXPECTED_NODEIDS = tuple(sorted(item.split(":")[0] + "." + item.split(":")[1] for item in METHODS))


class NativeSourceError(ValueError):
    """A pinned verifier input is missing or differs from the declared bytes."""


def selection_manifest(upstream):
    """Check pinned reference assertions; both roles use the same selection."""
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


def native_arguments(driver):
    """Exact public unittest methods; no discovery, config, plugin or pool."""
    return list(METHODS)


def validate_summary(value):
    required = {"schema_version", "selected", "selected_count", "run_count",
                "exit_code", "reports", "duplicate_reports", "skips", "errors", "failures", "source_provenance"}
    if not isinstance(value, dict) or set(value) != required:
        return "native summary schema mismatch"
    for key in ("schema_version", "selected_count", "run_count", "exit_code"):
        if type(value[key]) is not int or value[key] < 0:
            return f"native {key} must be a nonnegative integer"
    if value["schema_version"] != 1:
        return "native summary version mismatch"
    selected = value["selected"]
    if (not isinstance(selected, list) or len(selected) != EXPECTED_COUNT
            or value["selected_count"] != EXPECTED_COUNT
            or value["run_count"] != EXPECTED_COUNT
            or not all(isinstance(item, str) for item in selected)
            or len(set(selected)) != EXPECTED_COUNT
            or set(selected) != set(EXPECTED_NODEIDS)):
        return "native selected/run test count or identity mismatch"
    if value["exit_code"] or any(value[k] != [] for k in ("errors", "failures", "skips", "duplicate_reports")):
        return "native failed, skipped, duplicated, or incomplete tests"
    reports = value["reports"]
    if not isinstance(reports, dict) or set(reports) != set(selected):
        return "native missing or extra reports"
    if any(row != {"call": "passed"} for row in reports.values()):
        return "native test outcome was not passed"
    provenance = value['source_provenance']
    if (not isinstance(provenance, dict) or set(provenance) != {'sqlglot', 'parser'}
            or not all(isinstance(path, str) and path for path in provenance.values())):
        return "native import provenance missing"
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
"""Staged unchanged public unittest assertions; no oracle/reward authority."""
import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

source, driver, methods = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])

class Reports(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reports = {}
        self.duplicate_reports = []

    def addSuccess(self, test):
        super().addSuccess(test)
        if test.id() in self.reports:
            self.duplicate_reports.append(test.id())
        self.reports[test.id()] = {"call": "passed"}

with contextlib.redirect_stdout(sys.stderr):
    for name, rel in (("tests", "tests"), ("tests.dialects", "tests/dialects")):
        package = types.ModuleType(name)
        package.__path__ = [str(driver / rel)]
        sys.modules[name] = package
    sys.path.insert(0, source)
    modules = {}
    for item in methods:
        module_name = item.split(":")[0]
        if module_name not in modules:
            path = driver / (module_name.replace(".", "/") + ".py")
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            modules[module_name] = module
    import sqlglot
    import sqlglot.parser as parser_module
    source_root = Path(source).resolve()
    provenance = {'sqlglot': str(Path(sqlglot.__file__).resolve()),
                  'parser': str(Path(parser_module.__file__).resolve())}
    if not all(Path(path).is_relative_to(source_root) for path in provenance.values()):
        raise RuntimeError('Native tests imported a non-candidate SQLGlot checkout')
    suite = unittest.TestSuite()
    for item in methods:
        module_name, qualified = item.split(":")
        class_name, method = qualified.split(".")
        suite.addTest(getattr(modules[module_name], class_name)(method))
    selected = [test.id() for test in suite]
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, resultclass=Reports).run(suite)
    code = 0 if result.wasSuccessful() and not result.skipped else 1
print(json.dumps({
    "schema_version": 1, "selected": selected, "selected_count": len(selected),
    "run_count": result.testsRun, "exit_code": code, "reports": result.reports,
    "duplicate_reports": result.duplicate_reports,
    "skips": [test.id() for test, _ in result.skipped],
    "errors": [test.id() for test, _ in result.errors],
    "failures": [test.id() for test, _ in result.failures],
    "source_provenance": provenance,
}, sort_keys=True, allow_nan=False))
sys.exit(code)
'''


def _stage(upstream, driver, manifest):
    """Stage unchanged pinned public unittest inputs with their relative paths."""
    driver.mkdir(mode=0o755)
    for relative, expected in manifest["files"].items():
        data = (Path(upstream) / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise NativeSourceError("protected native input changed during staging")
        target = driver / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "bootstrap.py").chmod(0o444)
    for directory, _, _ in os.walk(driver):
        Path(directory).chmod(0o555)


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
               str(source), str(driver), json.dumps(native_arguments(driver))]
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
        if not reason and summary['source_provenance'] != {
                'sqlglot': str(source/'sqlglot/__init__.py'),
                'parser': str(source/'sqlglot/parser.py')}:
            reason = 'native import provenance differs from role snapshot'
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
