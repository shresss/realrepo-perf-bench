"""Bounded protected Jinja regression selection.

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

SOURCE_COMMIT = "09ddf2db4362e461339c5122eb232512723eb126"
PROTECTED_FILES = {'tests/test_core_tags.py': '189c0aa58cad4eb4d2191f2d9c00130da9767780885152fda41908d6239fb61c', 'tests/test_lexnparse.py': 'afbd393f3982661dc39a45e835a5c8e878df6d740c85831449f2680f10c458e2', 'tests/test_security.py': '0f0b0d74eed84bf7d44c1dd4e6d03642ec5830a35d6051939d39cefcf6ae6b4a', 'tests/test_tests.py': 'ae5e5439cf451e247bd21ab57778d5de67964b7ffdb9198ced7079d2540b53c3', 'tests/test_ext.py': '2536487db94b0ef33954bdc0b95974fe93d10652e2f6058b21aa90991b32fbd3', 'tests/conftest.py': '16aae731b661673e41469fdb37086644d53c900efaa9b36475af70634e2c141a'}
TEST_FILE = "test_core_tags.py"
SELECTION = ""
EXPECTED_NODEIDS = ('test_core_tags.py::TestForLoop::test_call_in_loop', 'test_core_tags.py::TestForLoop::test_changed', 'test_core_tags.py::TestForLoop::test_context_vars', 'test_core_tags.py::TestForLoop::test_cycling', 'test_core_tags.py::TestForLoop::test_else', 'test_core_tags.py::TestForLoop::test_else_scoping_item', 'test_core_tags.py::TestForLoop::test_empty_blocks', 'test_core_tags.py::TestForLoop::test_intended_scoping_with_set', 'test_core_tags.py::TestForLoop::test_lookaround', 'test_core_tags.py::TestForLoop::test_loop_errors', 'test_core_tags.py::TestForLoop::test_loop_filter', 'test_core_tags.py::TestForLoop::test_loop_unassignable', 'test_core_tags.py::TestForLoop::test_looploop', 'test_core_tags.py::TestForLoop::test_noniter', 'test_core_tags.py::TestForLoop::test_recursive', 'test_core_tags.py::TestForLoop::test_recursive_depth', 'test_core_tags.py::TestForLoop::test_recursive_depth0', 'test_core_tags.py::TestForLoop::test_recursive_empty_loop_iter', 'test_core_tags.py::TestForLoop::test_recursive_lookaround', 'test_core_tags.py::TestForLoop::test_reversed_bug', 'test_core_tags.py::TestForLoop::test_scope', 'test_core_tags.py::TestForLoop::test_scoped_loop_var', 'test_core_tags.py::TestForLoop::test_scoped_special_var', 'test_core_tags.py::TestForLoop::test_scoping_bug', 'test_core_tags.py::TestForLoop::test_simple', 'test_core_tags.py::TestForLoop::test_unpacking', 'test_core_tags.py::TestForLoop::test_varlen', 'test_core_tags.py::TestIfCondition::test_complete', 'test_core_tags.py::TestIfCondition::test_elif', 'test_core_tags.py::TestIfCondition::test_elif_deep', 'test_core_tags.py::TestIfCondition::test_else', 'test_core_tags.py::TestIfCondition::test_empty', 'test_core_tags.py::TestIfCondition::test_no_scope', 'test_core_tags.py::TestIfCondition::test_simple', 'test_core_tags.py::TestMacros::test_arguments', 'test_core_tags.py::TestMacros::test_arguments_defaults_nonsense', 'test_core_tags.py::TestMacros::test_caller_defaults_nonsense', 'test_core_tags.py::TestMacros::test_caller_undefined', 'test_core_tags.py::TestMacros::test_callself', 'test_core_tags.py::TestMacros::test_complex_call', 'test_core_tags.py::TestMacros::test_include', 'test_core_tags.py::TestMacros::test_macro_api', 'test_core_tags.py::TestMacros::test_macro_defaults_self_ref', 'test_core_tags.py::TestMacros::test_scoping', 'test_core_tags.py::TestMacros::test_simple', 'test_core_tags.py::TestMacros::test_simple_call', 'test_core_tags.py::TestMacros::test_varargs', 'test_core_tags.py::TestSet::test_block', 'test_core_tags.py::TestSet::test_block_escaping', 'test_core_tags.py::TestSet::test_block_escaping_filtered', 'test_core_tags.py::TestSet::test_block_filtered', 'test_core_tags.py::TestSet::test_block_filtered_set', 'test_core_tags.py::TestSet::test_init_namespace', 'test_core_tags.py::TestSet::test_namespace', 'test_core_tags.py::TestSet::test_namespace_block', 'test_core_tags.py::TestSet::test_namespace_loop', 'test_core_tags.py::TestSet::test_namespace_macro', 'test_core_tags.py::TestSet::test_namespace_redefined', 'test_core_tags.py::TestSet::test_normal', 'test_core_tags.py::TestSet::test_set_invalid', 'test_core_tags.py::TestWith::test_with', 'test_core_tags.py::TestWith::test_with_argument_scoping', 'test_ext.py::TestExtensions::test_do', 'test_lexnparse.py::TestLexer::test_balancing', 'test_lexnparse.py::TestLexer::test_bytefallback', 'test_lexnparse.py::TestLexer::test_comments', 'test_lexnparse.py::TestLexer::test_name[1a-False-False]', 'test_lexnparse.py::TestLexer::test_name[\\U0001f40d-False-False]', 'test_lexnparse.py::TestLexer::test_name[\\u1885-False-True]', 'test_lexnparse.py::TestLexer::test_name[\\u1886-False-True]', 'test_lexnparse.py::TestLexer::test_name[\\u2118-False-True]', 'test_lexnparse.py::TestLexer::test_name[\\u212e-False-True]', 'test_lexnparse.py::TestLexer::test_name[\\u304d-False-True]', 'test_lexnparse.py::TestLexer::test_name[\\xb7-False-False]', 'test_lexnparse.py::TestLexer::test_name[_-True-True]', 'test_lexnparse.py::TestLexer::test_name[a--False-False]', 'test_lexnparse.py::TestLexer::test_name[a\\U0001f40d-False-False]', 'test_lexnparse.py::TestLexer::test_name[a\\xb7-False-True]', 'test_lexnparse.py::TestLexer::test_name[f\\xf6\\xf6-False-True]', 'test_lexnparse.py::TestLexer::test_name[foo-True-True]', 'test_lexnparse.py::TestLexer::test_normalizing', 'test_lexnparse.py::TestLexer::test_operators', 'test_lexnparse.py::TestLexer::test_raw1', 'test_lexnparse.py::TestLexer::test_raw2', 'test_lexnparse.py::TestLexer::test_raw3', 'test_lexnparse.py::TestLexer::test_raw4', 'test_lexnparse.py::TestLexer::test_string_escapes', 'test_lexnparse.py::TestLexer::test_trailing_newline', 'test_lexnparse.py::TestLstripBlocks::test_comment_syntax', 'test_lexnparse.py::TestLstripBlocks::test_erb_syntax', 'test_lexnparse.py::TestLstripBlocks::test_erb_syntax_no_lstrip', 'test_lexnparse.py::TestLstripBlocks::test_erb_syntax_with_manual', 'test_lexnparse.py::TestLstripBlocks::test_lstrip', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_angle_bracket', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_angle_bracket_comment', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_angle_bracket_compact', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_angle_bracket_simple', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_blocks_false_with_no_lstrip', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_comment', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_embeded_strings', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_endline', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_inline', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_left_chars', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_nested', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_preserve_leading_newlines', 'test_lexnparse.py::TestLstripBlocks::test_lstrip_trim', 'test_lexnparse.py::TestLstripBlocks::test_no_lstrip', 'test_lexnparse.py::TestLstripBlocks::test_php_syntax', 'test_lexnparse.py::TestLstripBlocks::test_php_syntax_compact', 'test_lexnparse.py::TestLstripBlocks::test_php_syntax_with_manual', 'test_lexnparse.py::TestParser::test_balancing', 'test_lexnparse.py::TestParser::test_comment_syntax', 'test_lexnparse.py::TestParser::test_erb_syntax', 'test_lexnparse.py::TestParser::test_error_messages', 'test_lexnparse.py::TestParser::test_line_syntax', 'test_lexnparse.py::TestParser::test_line_syntax_priority', 'test_lexnparse.py::TestParser::test_php_syntax', 'test_lexnparse.py::TestParser::test_start_comment', 'test_lexnparse.py::TestSyntax::test_attr', 'test_lexnparse.py::TestSyntax::test_block_end_name', 'test_lexnparse.py::TestSyntax::test_bool', 'test_lexnparse.py::TestSyntax::test_call', 'test_lexnparse.py::TestSyntax::test_collection_literal[()]', 'test_lexnparse.py::TestSyntax::test_collection_literal[[]]', 'test_lexnparse.py::TestSyntax::test_collection_literal[{}]', 'test_lexnparse.py::TestSyntax::test_compare[1->-0]', 'test_lexnparse.py::TestSyntax::test_compare[1->=-1]', 'test_lexnparse.py::TestSyntax::test_compare[2-<-3]', 'test_lexnparse.py::TestSyntax::test_compare[3-<=-4]', 'test_lexnparse.py::TestSyntax::test_compare[4-!=-5]', 'test_lexnparse.py::TestSyntax::test_compare[4-==-4]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ 4 < 2 < 3 }}-False]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ 4 > 2 < 3 }}-True]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ 4 > 2 > 3 }}-False]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ a < b < c }}-False]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ a > b < c }}-True]', 'test_lexnparse.py::TestSyntax::test_compare_compound[{{ a > b > c }}-False]', 'test_lexnparse.py::TestSyntax::test_compare_parens', 'test_lexnparse.py::TestSyntax::test_concat', 'test_lexnparse.py::TestSyntax::test_conditional_expression', 'test_lexnparse.py::TestSyntax::test_const', 'test_lexnparse.py::TestSyntax::test_const_assign', 'test_lexnparse.py::TestSyntax::test_constant_casing', 'test_lexnparse.py::TestSyntax::test_div', 'test_lexnparse.py::TestSyntax::test_django_attr', 'test_lexnparse.py::TestSyntax::test_filter_priority', 'test_lexnparse.py::TestSyntax::test_function_calls', 'test_lexnparse.py::TestSyntax::test_grouping', 'test_lexnparse.py::TestSyntax::test_implicit_subscribed_tuple', 'test_lexnparse.py::TestSyntax::test_inop', 'test_lexnparse.py::TestSyntax::test_localset', 'test_lexnparse.py::TestSyntax::test_math', 'test_lexnparse.py::TestSyntax::test_neg_filter_priority', 'test_lexnparse.py::TestSyntax::test_notin', 'test_lexnparse.py::TestSyntax::test_numeric_literal[1-1]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[1.2-1.2]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[10e1-100.0]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[123-123]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[12_34_56-123456]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[1_2.3_4e5_6-1.234e+57]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[1e0-1.0]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[2.5e+100-2.5e+100]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[2.5e100-2.5e+100]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[25.6e-10-2.56e-09]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[34.56-34.56]', 'test_lexnparse.py::TestSyntax::test_numeric_literal[3_4.5_6-34.56]', 'test_lexnparse.py::TestSyntax::test_operator_precedence', 'test_lexnparse.py::TestSyntax::test_parse_unary', 'test_lexnparse.py::TestSyntax::test_raw2', 'test_lexnparse.py::TestSyntax::test_short_conditional_expression', 'test_lexnparse.py::TestSyntax::test_slicing', 'test_lexnparse.py::TestSyntax::test_string_concatenation', 'test_lexnparse.py::TestSyntax::test_subscript', 'test_lexnparse.py::TestSyntax::test_test_chaining', 'test_lexnparse.py::TestSyntax::test_trailing_comma', 'test_lexnparse.py::TestSyntax::test_tuple', 'test_lexnparse.py::TestSyntax::test_tuple_expr', 'test_lexnparse.py::TestSyntax::test_unary', 'test_lexnparse.py::TestTokenStream::test_iter', 'test_lexnparse.py::TestTokenStream::test_simple', 'test_security.py::TestSandbox::test_attr_filter', 'test_security.py::TestSandbox::test_binary_operator_intercepting', 'test_security.py::TestSandbox::test_immutable_environment', 'test_security.py::TestSandbox::test_markup_operations', 'test_security.py::TestSandbox::test_restricted', 'test_security.py::TestSandbox::test_template_data', 'test_security.py::TestSandbox::test_unary_operator_intercepting', 'test_security.py::TestSandbox::test_unsafe', 'test_security.py::TestStringFormat::test_basic_format_all_okay', 'test_security.py::TestStringFormat::test_basic_format_safety', 'test_security.py::TestStringFormat::test_safe_format_all_okay', 'test_security.py::TestStringFormat::test_safe_format_safety', 'test_security.py::TestStringFormatMap::test_basic_format_all_okay', 'test_security.py::TestStringFormatMap::test_basic_format_safety', 'test_security.py::TestStringFormatMap::test_safe_format_all_okay', 'test_tests.py::TestTestsCase::test_compare_aliases[eq 2-True]', 'test_tests.py::TestTestsCase::test_compare_aliases[eq 3-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[ge 2-True]', 'test_tests.py::TestTestsCase::test_compare_aliases[ge 3-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[gt 1-True]', 'test_tests.py::TestTestsCase::test_compare_aliases[gt 2-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[le 1-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[le 2-True]', 'test_tests.py::TestTestsCase::test_compare_aliases[lt 2-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[lt 3-True]', 'test_tests.py::TestTestsCase::test_compare_aliases[ne 2-False]', 'test_tests.py::TestTestsCase::test_compare_aliases[ne 3-True]', 'test_tests.py::TestTestsCase::test_defined', 'test_tests.py::TestTestsCase::test_equalto', 'test_tests.py::TestTestsCase::test_escaped', 'test_tests.py::TestTestsCase::test_even', 'test_tests.py::TestTestsCase::test_greaterthan', 'test_tests.py::TestTestsCase::test_in', 'test_tests.py::TestTestsCase::test_lessthan', 'test_tests.py::TestTestsCase::test_lower', 'test_tests.py::TestTestsCase::test_multiple_tests', 'test_tests.py::TestTestsCase::test_no_paren_for_arg1', 'test_tests.py::TestTestsCase::test_odd', 'test_tests.py::TestTestsCase::test_sameas', 'test_tests.py::TestTestsCase::test_types["foo" is callable-False]', 'test_tests.py::TestTestsCase::test_types["foo" is iterable-True]', 'test_tests.py::TestTestsCase::test_types["foo" is mapping-False]', 'test_tests.py::TestTestsCase::test_types["foo" is sequence-True]', 'test_tests.py::TestTestsCase::test_types["foo" is string-True]', 'test_tests.py::TestTestsCase::test_types[(10 ** 100) is float-False]', 'test_tests.py::TestTestsCase::test_types[(10 ** 100) is integer-True]', 'test_tests.py::TestTestsCase::test_types[(10 ** 100) is number-True]', 'test_tests.py::TestTestsCase::test_types[0 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[0 is false-False]', 'test_tests.py::TestTestsCase::test_types[0 is true-False]', 'test_tests.py::TestTestsCase::test_types[0.0 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[1 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[1 is false-False]', 'test_tests.py::TestTestsCase::test_types[1 is true-False]', 'test_tests.py::TestTestsCase::test_types[1.0 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[3.14159 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[3.14159 is integer-False]', 'test_tests.py::TestTestsCase::test_types[3.14159 is number-True]', 'test_tests.py::TestTestsCase::test_types[4.2 is float-True]', 'test_tests.py::TestTestsCase::test_types[42 is boolean-False]', 'test_tests.py::TestTestsCase::test_types[42 is callable-False]', 'test_tests.py::TestTestsCase::test_types[42 is false-False]', 'test_tests.py::TestTestsCase::test_types[42 is float-False]', 'test_tests.py::TestTestsCase::test_types[42 is integer-True]', 'test_tests.py::TestTestsCase::test_types[42 is iterable-False]', 'test_tests.py::TestTestsCase::test_types[42 is mapping-False]', 'test_tests.py::TestTestsCase::test_types[42 is none-False]', 'test_tests.py::TestTestsCase::test_types[42 is number-True]', 'test_tests.py::TestTestsCase::test_types[42 is sequence-False]', 'test_tests.py::TestTestsCase::test_types[42 is string-False]', 'test_tests.py::TestTestsCase::test_types[42 is true-False]', 'test_tests.py::TestTestsCase::test_types[[1, 2, 3] is sequence-True]', 'test_tests.py::TestTestsCase::test_types[[] is callable-False]', 'test_tests.py::TestTestsCase::test_types[[] is iterable-True]', 'test_tests.py::TestTestsCase::test_types[[] is mapping-False]', 'test_tests.py::TestTestsCase::test_types[[] is sequence-True]', 'test_tests.py::TestTestsCase::test_types[complex is number-True]', 'test_tests.py::TestTestsCase::test_types[false is boolean-True]', 'test_tests.py::TestTestsCase::test_types[false is callable-False]', 'test_tests.py::TestTestsCase::test_types[false is false-True]', 'test_tests.py::TestTestsCase::test_types[false is float-False]', 'test_tests.py::TestTestsCase::test_types[false is integer-False]', 'test_tests.py::TestTestsCase::test_types[false is iterable-False]', 'test_tests.py::TestTestsCase::test_types[false is mapping-False]', 'test_tests.py::TestTestsCase::test_types[false is none-False]', 'test_tests.py::TestTestsCase::test_types[false is number-True]', 'test_tests.py::TestTestsCase::test_types[false is sequence-False]', 'test_tests.py::TestTestsCase::test_types[false is string-False]', 'test_tests.py::TestTestsCase::test_types[false is true-False]', 'test_tests.py::TestTestsCase::test_types[mydict is mapping-True]', 'test_tests.py::TestTestsCase::test_types[none is boolean-False]', 'test_tests.py::TestTestsCase::test_types[none is callable-False]', 'test_tests.py::TestTestsCase::test_types[none is false-False]', 'test_tests.py::TestTestsCase::test_types[none is float-False]', 'test_tests.py::TestTestsCase::test_types[none is integer-False]', 'test_tests.py::TestTestsCase::test_types[none is iterable-False]', 'test_tests.py::TestTestsCase::test_types[none is mapping-False]', 'test_tests.py::TestTestsCase::test_types[none is none-True]', 'test_tests.py::TestTestsCase::test_types[none is number-False]', 'test_tests.py::TestTestsCase::test_types[none is sequence-False]', 'test_tests.py::TestTestsCase::test_types[none is string-False]', 'test_tests.py::TestTestsCase::test_types[none is true-False]', 'test_tests.py::TestTestsCase::test_types[range is callable-True]', 'test_tests.py::TestTestsCase::test_types[range(5) is iterable-True]', 'test_tests.py::TestTestsCase::test_types[true is boolean-True]', 'test_tests.py::TestTestsCase::test_types[true is false-False]', 'test_tests.py::TestTestsCase::test_types[true is float-False]', 'test_tests.py::TestTestsCase::test_types[true is integer-False]', 'test_tests.py::TestTestsCase::test_types[true is none-False]', 'test_tests.py::TestTestsCase::test_types[true is number-True]', 'test_tests.py::TestTestsCase::test_types[true is string-False]', 'test_tests.py::TestTestsCase::test_types[true is true-True]', 'test_tests.py::TestTestsCase::test_types[{} is callable-False]', 'test_tests.py::TestTestsCase::test_types[{} is iterable-True]', 'test_tests.py::TestTestsCase::test_types[{} is mapping-True]', 'test_tests.py::TestTestsCase::test_types[{} is sequence-True]', 'test_tests.py::TestTestsCase::test_upper')
EXPECTED_COUNT = len(EXPECTED_NODEIDS)



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
        *[str(driver / f) for f in ("test_core_tags.py", "test_lexnparse.py", "test_security.py", "test_tests.py")],
        str(driver / "test_ext.py") + "::TestExtensions::test_do", "-q", "-k", SELECTION,
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

source, driver, arguments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
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
    # If tests import repo helper modules (e.g. tests/helpers.py), load them from
    # `driver` with importlib like the pyjanitor adapter did for strategies.py.
    # If they need conftest fixtures, load that conftest from `driver` and pass it
    # in plugins=[collector, conftest_module]; --noconftest stays on.
    import jinja2
    if not Path(jinja2.__file__).resolve().is_relative_to(Path(source).resolve()):
        raise RuntimeError("native source import escaped snapshot")
    spec = importlib.util.spec_from_file_location("protected_jinja_conftest", driver / "conftest.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    exit_code = int(pytest.main(arguments, plugins=[collector, fixtures]))

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
    (driver / "pytest.ini").write_text("[pytest]\naddopts =\n")
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
