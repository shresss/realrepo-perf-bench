"""Bounded, protected upstream regression selection for pypdf-3679-name-quadratic.

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

# ---- task-specific block. Values from the public PR commit's test files (3a4e913c);
# both baseline and candidate run this same protected selection.
SOURCE_COMMIT = "3a4e913c4cbee207d72fd63d835740ad9825d1bf"
# Repo-relative paths of protected assertion inputs -> sha256 of the reference bytes.
# pypdf's test modules do "from . import ..." / "from .utils import ...", so _stage() keeps them in a
# driver/tests/ package (basenames still unique) instead of flattening them into the driver root.
PROTECTED_FILES = {
    "tests/__init__.py": "04c361657f49603094b0eddfe2e4fa5065879cb6fe8ac825dd11262f03c89511",
    "tests/utils.py": "c0314f102094c3d4e5ededef182f0a05074144832bdc10ec823617104bbf0134",
    "tests/test_utils.py": "67f4deca2218dbae97bb8ebf2b148f4a9a932046dea7aa75e1d66237669da0de",
    "tests/test_generic.py": "c7693c7162364e5040b46a740a5e1ce615b5d93b4d572048c3889db055eddd66",
}
TEST_FILES = ("tests/test_utils.py", "tests/test_generic.py")  # pytest files inside the driver dir
# Whole modules (the PR's new read_until_regex tests live in test_utils.py; NameObject read/write tests in
# test_generic.py) minus five tests that open files from the repository's resources/ directory, which is not staged,
# and test_rename_kwargs__stacklevel, which spawns a Python subprocess (workers run with RLIMIT_NPROC 1).
SELECTION = ("not (test_remove_child_in_tree or test_encodedstream_set_data or test_is_null_or_none"
             " or test_coverage_arrayobject or test_coverage_streamobject or test_rename_kwargs__stacklevel)")
EXPECTED_NODEIDS = tuple(sorted((
    'tests/test_utils.py::test_skip_over_whitespace[stream0-False]',
    'tests/test_utils.py::test_skip_over_whitespace[stream1-False]',
    'tests/test_utils.py::test_skip_over_whitespace[stream2-True]',
    'tests/test_utils.py::test_skip_over_whitespace[stream3-True]',
    'tests/test_utils.py::test_skip_over_whitespace[stream4-True]',
    'tests/test_utils.py::test_skip_over_whitespace[stream5-True]',
    'tests/test_utils.py::test_skip_over_whitespace[stream6-True]',
    'tests/test_utils.py::test_check_if_whitespace_only[foo-False]',
    'tests/test_utils.py::test_check_if_whitespace_only[ a-False]',
    'tests/test_utils.py::test_check_if_whitespace_only[ a\\n b-False]',
    'tests/test_utils.py::test_check_if_whitespace_only[-True]',
    'tests/test_utils.py::test_check_if_whitespace_only[ -True]',
    'tests/test_utils.py::test_check_if_whitespace_only[  -True]',
    'tests/test_utils.py::test_check_if_whitespace_only[  \\n-True]',
    'tests/test_utils.py::test_check_if_whitespace_only[    \\n-True]',
    'tests/test_utils.py::test_check_if_whitespace_only[\\x0c-True]',
    'tests/test_utils.py::test_read_until_whitespace',
    'tests/test_utils.py::test_skip_over_comment[stream0-]',
    'tests/test_utils.py::test_skip_over_comment[stream1-]',
    'tests/test_utils.py::test_skip_over_comment[stream2- ]',
    'tests/test_utils.py::test_skip_over_comment[stream3-bar]',
    'tests/test_utils.py::test_read_until_regex_premature_ending_name',
    'tests/test_utils.py::test_read_until_regex_match_in_first_chunk',
    'tests/test_utils.py::test_read_until_regex_match_in_second_chunk',
    'tests/test_utils.py::test_read_until_regex_match_at_chunk_boundary',
    'tests/test_utils.py::test_read_until_regex_multi_byte_spanning_boundary',
    'tests/test_utils.py::test_read_until_regex_no_match_exhausted',
    'tests/test_utils.py::test_read_until_regex_exponential_chunk_growth',
    'tests/test_utils.py::test_read_until_regex_match_spanning_later_boundary',
    'tests/test_utils.py::test_read_until_regex_tail_overlap_is_fixed',
    'tests/test_utils.py::test_matrix_multiply[a0-b0-expected0]',
    'tests/test_utils.py::test_matrix_multiply[a1-b1-expected1]',
    'tests/test_utils.py::test_matrix_multiply[a2-b2-expected2]',
    'tests/test_utils.py::test_mark_location',
    'tests/test_utils.py::test_deprecate_no_replacement',
    'tests/test_utils.py::test_read_block_backwards[abc-1-0--1]',
    'tests/test_utils.py::test_read_block_backwards[abc-1-1-a-0]',
    'tests/test_utils.py::test_read_block_backwards[abc-2-1-b-1]',
    'tests/test_utils.py::test_read_block_backwards[abc-2-2-ab-0]',
    'tests/test_utils.py::test_read_block_backwards[abc-3-1-c-2]',
    'tests/test_utils.py::test_read_block_backwards[abc-3-2-bc-1]',
    'tests/test_utils.py::test_read_block_backwards[abc-3-3-abc-0]',
    'tests/test_utils.py::test_read_block_backwards[-0-1-None-0]',
    'tests/test_utils.py::test_read_block_backwards[a-0-1-None-0]',
    'tests/test_utils.py::test_read_block_backwards[abc-0-10-None-0]',
    'tests/test_utils.py::test_read_block_backwards_at_start',
    'tests/test_utils.py::test_read_previous_line[0]',
    'tests/test_utils.py::test_read_previous_line[1]',
    'tests/test_utils.py::test_read_previous_line[2]',
    'tests/test_utils.py::test_read_previous_line[3]',
    'tests/test_utils.py::test_read_previous_line[4]',
    'tests/test_utils.py::test_read_previous_line[5]',
    'tests/test_utils.py::test_read_previous_line[6]',
    'tests/test_utils.py::test_read_previous_line[7]',
    'tests/test_utils.py::test_read_previous_line2',
    'tests/test_utils.py::test_get_max_pdf_version_header',
    'tests/test_utils.py::test_read_block_backwards_exception',
    'tests/test_utils.py::test_deprecate_with_replacement',
    'tests/test_utils.py::test_deprecation_no_replacement',
    'tests/test_utils.py::test_rename_kwargs',
    'tests/test_utils.py::test_human_readable_bytes[123-123 Byte]',
    'tests/test_utils.py::test_human_readable_bytes[1234-1.2 kB]',
    'tests/test_utils.py::test_human_readable_bytes[123456-123.5 kB]',
    'tests/test_utils.py::test_human_readable_bytes[1234567-1.2 MB]',
    'tests/test_utils.py::test_human_readable_bytes[1234567890-1.2 GB]',
    'tests/test_utils.py::test_human_readable_bytes[1234567890000-1234.6 GB]',
    'tests/test_utils.py::test_file_class',
    'tests/test_utils.py::test_parse_datetime[D:20210318000756-2021-03-18T00:07:56]',
    'tests/test_utils.py::test_parse_datetime[20210318000756-2021-03-18T00:07:56]',
    'tests/test_utils.py::test_parse_datetime[D:2021-2021-01-01T00:00:00]',
    'tests/test_utils.py::test_parse_datetime[D:202103-2021-03-01T00:00:00]',
    'tests/test_utils.py::test_parse_datetime[D:20210304-2021-03-04T00:00:00]',
    'tests/test_utils.py::test_parse_datetime[D:2021030402-2021-03-04T02:00:00]',
    'tests/test_utils.py::test_parse_datetime[D:20210408054711-2021-04-08T05:47:11]',
    'tests/test_utils.py::test_parse_datetime[D:20210408054711Z-2021-04-08T05:47:11+00:00]',
    'tests/test_utils.py::test_parse_datetime[D:20210408054711Z00-2021-04-08T05:47:11+00:00]',
    'tests/test_utils.py::test_parse_datetime[D:20210408054711Z0000-2021-04-08T05:47:11+00:00]',
    "tests/test_utils.py::test_parse_datetime[D:20210408075331+02'00'-2021-04-08T07:53:31+02:00]",
    "tests/test_utils.py::test_parse_datetime[D:20210408075331-03'00'-2021-04-08T07:53:31-03:00]",
    'tests/test_utils.py::test_parse_datetime_edge_cases[-None]',
    'tests/test_utils.py::test_parse_datetime_edge_cases[None-None]',
    'tests/test_utils.py::test_parse_datetime_err',
    'tests/test_utils.py::test_format_iso8824_date',
    'tests/test_utils.py::test_format_iso8824_date_roundtrip',
    'tests/test_utils.py::test_is_sublist',
    'tests/test_utils.py::test_version_compare[1-2-True]',
    'tests/test_utils.py::test_version_compare[2-1-False]',
    'tests/test_utils.py::test_version_compare[1-1-False]',
    'tests/test_utils.py::test_version_compare[1.0-1.1-True]',
    'tests/test_utils.py::test_version_compare[1-1.1-True]',
    'tests/test_utils.py::test_version_compare[1a-2-True]',
    'tests/test_utils.py::test_version_compare[2a-1-False]',
    'tests/test_utils.py::test_version_compare[1a-1-False]',
    'tests/test_utils.py::test_version_compare[1.0a-1.1-True]',
    'tests/test_utils.py::test_version_compare[1a-1.1-False]',
    'tests/test_utils.py::test_version_compare[1-2a-True]',
    'tests/test_utils.py::test_version_compare[2-1a-False]',
    'tests/test_utils.py::test_version_compare[1-1a-True]',
    'tests/test_utils.py::test_version_compare[1.0-1.1a-True]',
    'tests/test_utils.py::test_version_compare[1-1.1a-True]',
    'tests/test_utils.py::test_version_compare[-0.0.0-True]',
    'tests/test_utils.py::test_version_compare[1.0a-1.0-False]',
    'tests/test_utils.py::test_version_compare[1.0-1.0a-True]',
    'tests/test_utils.py::test_version_compare_equal_str',
    'tests/test_utils.py::test_version_compare_lt_str',
    'tests/test_utils.py::test_bad_version',
    'tests/test_utils.py::test_version_eq_hash',
    'tests/test_utils.py::test_classproperty',
    'tests/test_generic.py::test_float_object_exception',
    'tests/test_generic.py::test_number_object_exception',
    'tests/test_generic.py::test_number_object_no_exception',
    'tests/test_generic.py::test_create_string_object_exception',
    'tests/test_generic.py::test_boolean_object[true-true-4]',
    'tests/test_generic.py::test_boolean_object[false-false-5]',
    'tests/test_generic.py::test_boolean_object_write',
    'tests/test_generic.py::test_boolean_eq',
    'tests/test_generic.py::test_boolean_object_exception',
    'tests/test_generic.py::test_array_object_exception',
    'tests/test_generic.py::test_null_object_exception',
    'tests/test_generic.py::test_indirect_object_premature[]',
    'tests/test_generic.py::test_indirect_object_premature[False]',
    'tests/test_generic.py::test_indirect_object_premature[foo ]',
    'tests/test_generic.py::test_indirect_object_premature[foo  ]',
    'tests/test_generic.py::test_indirect_object_premature[foo bar]',
    'tests/test_generic.py::test_read_hex_string_from_stream',
    'tests/test_generic.py::test_read_hex_string_from_stream_exception',
    'tests/test_generic.py::test_read_string_from_stream_exception',
    'tests/test_generic.py::test_read_string_from_stream_not_in_escapedict_no_digit',
    'tests/test_generic.py::test_read_string_from_stream_multichar_eol',
    'tests/test_generic.py::test_read_string_from_stream_multichar_eol2',
    'tests/test_generic.py::test_read_string_from_stream_excape_digit',
    'tests/test_generic.py::test_read_string_from_stream_excape_digit2',
    'tests/test_generic.py::test_name_object',
    'tests/test_generic.py::test_destination_fit_r',
    'tests/test_generic.py::test_destination_fit_v',
    'tests/test_generic.py::test_outline_item_write_to_stream',
    'tests/test_generic.py::test_encode_pdfdocencoding_keyerror',
    'tests/test_generic.py::test_encode_pdfdocencoding_returns_bytes[]',
    'tests/test_generic.py::test_encode_pdfdocencoding_returns_bytes[data]',
    'tests/test_generic.py::test_read_object_comment_exception',
    'tests/test_generic.py::test_read_object_empty',
    'tests/test_generic.py::test_read_object_empty_in_array',
    'tests/test_generic.py::test_read_object_invalid',
    'tests/test_generic.py::test_read_object_comment',
    'tests/test_generic.py::test_bytestringobject',
    'tests/test_generic.py::test_dictionaryobject_key_is_no_pdfobject',
    'tests/test_generic.py::test_dictionaryobject_xmp_meta',
    'tests/test_generic.py::test_dictionaryobject_value_is_no_pdfobject',
    'tests/test_generic.py::test_dictionaryobject_setdefault_key_is_no_pdfobject',
    'tests/test_generic.py::test_dictionaryobject_setdefault_value_is_no_pdfobject',
    'tests/test_generic.py::test_dictionaryobject_setdefault_value',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_broken',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_unexpected_end',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_no_newline',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_no_stream_length[True]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_no_stream_length[False]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_stream_valid[True-6-False]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_stream_valid[True-10-False]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_stream_valid[True-4-True]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_stream_valid[False-6-False]',
    'tests/test_generic.py::test_dictionaryobject_read_from_stream_stream_stream_valid[False-10-False]',
    'tests/test_generic.py::test_rectangleobject',
    'tests/test_generic.py::test_textstringobject_exc',
    'tests/test_generic.py::test_textstringobject_autodetect_utf16',
    'tests/test_generic.py::test_textstringobject__numbers_as_input',
    'tests/test_generic.py::test_remove_child_not_in_tree',
    'tests/test_generic.py::test_remove_child_not_in_that_tree',
    'tests/test_generic.py::test_remove_child_not_found_in_tree',
    'tests/test_generic.py::test_remove_child_found_in_tree',
    'tests/test_generic.py::test_checkboxradiobuttonattributes_opt',
    'tests/test_generic.py::test_name_object_invalid_decode',
    'tests/test_generic.py::test_indirect_object_invalid_read',
    'tests/test_generic.py::test_create_string_object_utf16_bom',
    'tests/test_generic.py::test_create_string_object_force',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.000000-0.0]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.0-0.0_0]',
    'tests/test_generic.py::test_float_object_decimal_to_string[1.0-1_0]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.123000-0.123]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.000123000-0.000123]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.0-0.0_1]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0-0.0]',
    'tests/test_generic.py::test_float_object_decimal_to_string[1-1]',
    'tests/test_generic.py::test_float_object_decimal_to_string[1.0-1_1]',
    'tests/test_generic.py::test_float_object_decimal_to_string[1.01-1.01]',
    'tests/test_generic.py::test_float_object_decimal_to_string[1.010-1.01]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0000.0000-0.0]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.10101010-0.1010101]',
    'tests/test_generic.py::test_float_object_decimal_to_string[50000000000-50000000000]',
    'tests/test_generic.py::test_float_object_decimal_to_string[99900000000000000123-99900000000000000000]',
    'tests/test_generic.py::test_float_object_decimal_to_string[99900000000000000123.456000-99900000000000000000]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.00000000000000000000123-0.00000000000000000000123]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.00000123-0.00000123]',
    'tests/test_generic.py::test_float_object_decimal_to_string[0.00000000000000000000123000-0.00000000000000000000123]',
    'tests/test_generic.py::test_float_object_decimal_to_string[-4.6--4.6]',
    'tests/test_generic.py::test_cloning',
    'tests/test_generic.py::test_cloning_indirect_obj_keeps_hard_reference',
    'tests/test_generic.py::test_cloning_null_obj_keeps_hard_reference',
    'tests/test_generic.py::test_indirect_object_contains',
    'tests/test_generic.py::test_indirect_object_iter',
    'tests/test_generic.py::test_array_operators',
    'tests/test_generic.py::test_unitary_extract_inline_buffer_invalid',
    'tests/test_generic.py::test_unitary_extract_inline',
    'tests/test_generic.py::test_missing_hashbin',
    'tests/test_generic.py::test_contentstream_arrayobject_containing_nullobject',
)))
EXPECTED_COUNT = len(EXPECTED_NODEIDS)  # must equal the Linux collection count exactly
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
        "marker_selection": "not enable_socket and not samples",
        "expected_count": EXPECTED_COUNT, "nodeids": list(EXPECTED_NODEIDS),
        "files": dict(PROTECTED_FILES),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {**manifest, "sha256": hashlib.sha256(encoded).hexdigest()}


def pytest_arguments(driver):
    """Return a fixed selection with all candidate discovery routes disabled."""
    driver = Path(driver)
    return [
        *(str(driver / name) for name in TEST_FILES), "-q", "-k", SELECTION,
        # Upstream CI's own exclusion: network downloads and the sample-files submodule.
        "-m", "not enable_socket and not samples",
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
import yaml  # noqa: F401  (tests/__init__.py imports it)
import PIL.Image  # noqa: F401  (tests/utils.py imports it)

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
    import pypdf  # noqa: F401
    assert os.path.realpath(pypdf.__file__).startswith(os.path.realpath(source) + os.sep), pypdf.__file__
    # The protected tests package is imported by pytest from the driver, never from source.
    assert "tests" not in sys.modules
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
    package = driver / "tests"
    package.mkdir(mode=0o755)
    for relative, expected in manifest["files"].items():
        data = (Path(upstream) / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise NativeSourceError("protected native input changed during staging")
        target = package / Path(relative).name
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n"
        "    slow: upstream marker\n    samples: upstream marker\n"
        "    enable_socket: upstream marker\n    timeout: upstream marker\n"
    )
    for path in driver.iterdir():
        if path.is_file():
            path.chmod(0o444)
    package.chmod(0o555)
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
