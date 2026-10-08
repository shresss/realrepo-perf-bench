"""Bounded, protected upstream regression selection for markdown-1621-inline-links (from the template).

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

# ---- task-specific block (markdown-1621-inline-links), filled from the REFERENCE commit's test files;
# both baseline and candidate run this same protected selection.
SOURCE_COMMIT = "152a16fb1a926eabbfc5ab1af83f2b6cf9979314"
# Repo-relative paths of protected assertion inputs -> sha256 of the reference bytes.
# _stage() FLATTENS them into one driver dir by basename: basenames must be unique.
PROTECTED_FILES = {
    "tests/test_syntax/inline/test_links.py":
        "3d07d7e936c27d1b79efd7c9686d554dd28c64a3625bcc37abe2f9136be8579a",
    "tests/test_syntax/inline/test_emphasis.py":
        "6726c073b3fd448ffbad50f52bdc8c63fe36653b910d27b0b598f98b6129ca0d",
    "tests/test_syntax/inline/test_images.py":
        "367fe315a1fc735bf0c1ec1a1fcc8717c0399576a570040cf42c31579c0de993",
    "tests/test_syntax/inline/test_autolinks.py":
        "d3d824008251679c2df679b85bd413e28b0c323bfc494540af3a350ba91bac6c",
    "tests/test_syntax/inline/test_raw_html.py":
        "6de14be7b3088a50bddab96dc7ccf9fe4ab1eb956fedd2de342031744038ceb1",
    "tests/test_syntax/inline/test_code.py":
        "3b5b9e8127e125a68bbebb47279069d4c03195077d841ebf0b88b65d3b4a66b2",
    "tests/test_syntax/inline/test_entities.py":
        "052917d6add2598d46a982a47d5e27ab067c52404dcc38fe7aba185d5022a20c",
    "tests/test_apis.py":
        "e8905c1424ff0c4ab3c5783edeab18226570367d8e6babc9880249a1dbc11d41",
    "tests/test_syntax/extensions/test_smarty.py":
        "b6f84c277162b323e71aa6bc4feb90d9462f91015147182033bd27b5a6463a9f",
    "tests/test_syntax/extensions/test_abbr.py":
        "a29c0906e794681761e66ec8f426932e94bc07f901093e120060b1f26fbfb97d",
    "tests/test_syntax/extensions/test_footnotes.py":
        "1fa66805cef0bed1c46352ce2e12dee112fe5d045c2ccee9464a5b377289c7df",
    "tests/test_syntax/extensions/test_attr_list.py":
        "91e771b19d368766e467b466c78024a369786cc5d08f380e5f7bf09de6a61d70",
    "tests/test_syntax/extensions/test_legacy_em.py":
        "aeed840531f124708815bb7b91ac4f657518dc788cf48ea20dbeb80150fa1d46",
}
TEST_FILES = ('test_links.py', 'test_emphasis.py', 'test_images.py', 'test_autolinks.py', 'test_raw_html.py', 'test_code.py', 'test_entities.py', 'test_apis.py', 'test_smarty.py', 'test_abbr.py', 'test_footnotes.py', 'test_attr_list.py', 'test_legacy_em.py')
TEST_FILE = TEST_FILES[0]
# Every test in the 13 protected files except the PR's new mechanism test, which asserts the search offset itself
# and does not terminate on the untouched checkout (out-of-scope hang fix for custom patterns, see CONTRACT.md).
SELECTION = "not testInlineProcessorAdvancesSearchIndex"
_NODEIDS = (
    'test_abbr.py::TestAbbr::test_abbr_bracket',
    'test_abbr.py::TestAbbr::test_abbr_carrot',
    'test_abbr.py::TestAbbr::test_abbr_clear',
    'test_abbr.py::TestAbbr::test_abbr_double_quoted',
    'test_abbr.py::TestAbbr::test_abbr_empty',
    'test_abbr.py::TestAbbr::test_abbr_extra_space',
    'test_abbr.py::TestAbbr::test_abbr_glossary',
    'test_abbr.py::TestAbbr::test_abbr_glossary_2',
    'test_abbr.py::TestAbbr::test_abbr_hyphen',
    'test_abbr.py::TestAbbr::test_abbr_ignore_backslash',
    'test_abbr.py::TestAbbr::test_abbr_ignore_unmatched_case',
    'test_abbr.py::TestAbbr::test_abbr_line_break',
    'test_abbr.py::TestAbbr::test_abbr_lower',
    'test_abbr.py::TestAbbr::test_abbr_multiple_in_tail',
    'test_abbr.py::TestAbbr::test_abbr_multiple_in_text',
    'test_abbr.py::TestAbbr::test_abbr_multiple_nested',
    'test_abbr.py::TestAbbr::test_abbr_nested',
    'test_abbr.py::TestAbbr::test_abbr_no_blank_Lines',
    'test_abbr.py::TestAbbr::test_abbr_no_space',
    'test_abbr.py::TestAbbr::test_abbr_override',
    'test_abbr.py::TestAbbr::test_abbr_partial_word',
    'test_abbr.py::TestAbbr::test_abbr_reset',
    'test_abbr.py::TestAbbr::test_abbr_single_quoted',
    'test_abbr.py::TestAbbr::test_abbr_superset_vs_subset',
    'test_abbr.py::TestAbbr::test_abbr_unused',
    'test_abbr.py::TestAbbr::test_abbr_upper',
    'test_abbr.py::TestAbbr::test_abbr_with_attr_list',
    'test_abbr.py::TestAbbr::test_ignore_atomic',
    'test_apis.py::TestMarkdownBasics::testBlankInput',
    'test_apis.py::TestMarkdownBasics::testDotNotationExtension',
    'test_apis.py::TestMarkdownBasics::testDotNotationExtensionWithClass',
    'test_apis.py::TestMarkdownBasics::testEntryPointExtension',
    'test_apis.py::TestMarkdownBasics::testInstanceExtension',
    'test_apis.py::TestMarkdownBasics::testSimpleInput',
    'test_apis.py::TestMarkdownBasics::testWhitespaceOnly',
    'test_apis.py::TestConvertFile::testFileNames',
    'test_apis.py::TestConvertFile::testFileObjects',
    'test_apis.py::TestConvertFile::testStdinStdout',
    'test_apis.py::TestBlockParser::testParseChunk',
    'test_apis.py::TestBlockParser::testParseDocument',
    'test_apis.py::TestBlockParserState::testBlankState',
    'test_apis.py::TestBlockParserState::testIsSate',
    'test_apis.py::TestBlockParserState::testReset',
    'test_apis.py::TestBlockParserState::testSetSate',
    'test_apis.py::TestHtmlStash::testReset',
    'test_apis.py::TestHtmlStash::testSimpleStore',
    'test_apis.py::TestHtmlStash::testStoreMore',
    'test_apis.py::RegistryTests::testCreateRegistry',
    'test_apis.py::RegistryTests::testDeregister',
    'test_apis.py::RegistryTests::testGetIndexForName',
    'test_apis.py::RegistryTests::testIsSorted',
    'test_apis.py::RegistryTests::testRegisterDupplicate',
    'test_apis.py::RegistryTests::testRegisterWithoutPriority',
    'test_apis.py::RegistryTests::testRegistryContains',
    'test_apis.py::RegistryTests::testRegistryDelItem',
    'test_apis.py::RegistryTests::testRegistryGetItemByIndex',
    'test_apis.py::RegistryTests::testRegistryGetItemByItem',
    'test_apis.py::RegistryTests::testRegistryIter',
    'test_apis.py::RegistryTests::testRegistrySetItem',
    'test_apis.py::RegistryTests::testRegistrySlice',
    'test_apis.py::RegistryTests::testSortRegistry',
    'test_apis.py::TestErrors::testBadOutputFormat',
    'test_apis.py::TestErrors::testBaseExtention',
    'test_apis.py::TestErrors::testDotNotationExtensionWithBadClass',
    'test_apis.py::TestErrors::testLoadBadExtension',
    'test_apis.py::TestErrors::testLoadExtensionFailure',
    'test_apis.py::TestErrors::testNonExtension',
    'test_apis.py::testETreeComments::testCommentIsBlockLevel',
    'test_apis.py::testETreeComments::testCommentIsComment',
    'test_apis.py::testETreeComments::testCommentPrettify',
    'test_apis.py::testETreeComments::testCommentSerialization',
    'test_apis.py::testElementTailTests::testBrTailNoNewline',
    'test_apis.py::testElementPreCodeTests::testPreCodeEmpty',
    'test_apis.py::testElementPreCodeTests::testPreCodeWithChildren',
    'test_apis.py::testElementPreCodeTests::testPreCodeWithSpaceOnly',
    'test_apis.py::testElementPreCodeTests::testPreCodeWithText',
    'test_apis.py::testElementPreCodeTests::testPreCodeWithTrailingSpace',
    'test_apis.py::testSerializers::testBadQNameTag',
    'test_apis.py::testSerializers::testHTMLOutput',
    'test_apis.py::testSerializers::testHtml',
    'test_apis.py::testSerializers::testMixedCaseTags',
    'test_apis.py::testSerializers::testProsessingInstruction',
    'test_apis.py::testSerializers::testQNameAttribute',
    'test_apis.py::testSerializers::testQNameEscaping',
    'test_apis.py::testSerializers::testQNamePreEscaping',
    'test_apis.py::testSerializers::testQNameTag',
    'test_apis.py::testSerializers::testRegisterSerializer',
    'test_apis.py::testSerializers::testXHTMLOutput',
    'test_apis.py::testSerializers::testXhtml',
    'test_apis.py::testAtomicString::testInlineProcessorDoesntCrashWithWrongAtomicString',
    'test_apis.py::testAtomicString::testNestedAtomicString',
    'test_apis.py::testAtomicString::testSimpleAtomicString',
    'test_apis.py::testAtomicString::testString',
    'test_apis.py::TestConfigParsing::testBooleansParsing',
    'test_apis.py::TestConfigParsing::testInvalidBooleansParsing',
    'test_apis.py::TestConfigParsing::testPreserveNone',
    'test_apis.py::TestCliOptionParsing::testEncodingOption',
    'test_apis.py::TestCliOptionParsing::testExtensionConfigOption',
    'test_apis.py::TestCliOptionParsing::testExtensionConfigOptionAsJSON',
    'test_apis.py::TestCliOptionParsing::testExtensionConfigOptionBadFormat',
    'test_apis.py::TestCliOptionParsing::testExtensionConfigOptionMissingFile',
    'test_apis.py::TestCliOptionParsing::testExtensionOption',
    'test_apis.py::TestCliOptionParsing::testInputAndOutputFileOptions',
    'test_apis.py::TestCliOptionParsing::testInputFileOption',
    'test_apis.py::TestCliOptionParsing::testMultipleExtensionOptions',
    'test_apis.py::TestCliOptionParsing::testNoLazyOlOption',
    'test_apis.py::TestCliOptionParsing::testNoOptions',
    'test_apis.py::TestCliOptionParsing::testNoisyOption',
    'test_apis.py::TestCliOptionParsing::testOutputFileOption',
    'test_apis.py::TestCliOptionParsing::testOutputFormatOption',
    'test_apis.py::TestCliOptionParsing::testQuietOption',
    'test_apis.py::TestCliOptionParsing::testVerboseOption',
    'test_apis.py::TestEscapeAppend::testAppend',
    'test_apis.py::TestBlockAppend::testBlockAppend',
    'test_apis.py::TestAncestorExclusion::test_ancestors',
    'test_apis.py::TestAncestorExclusion::test_ancestors_tail',
    'test_attr_list.py::TestAttrList::test_backslash_escape_value',
    'test_attr_list.py::TestAttrList::test_curly_after_block',
    'test_attr_list.py::TestAttrList::test_curly_after_inline',
    'test_attr_list.py::TestAttrList::test_curly_in_double_quote',
    'test_attr_list.py::TestAttrList::test_curly_in_single_quote',
    'test_attr_list.py::TestAttrList::test_empty_attr_list',
    'test_attr_list.py::TestAttrList::test_extra_eq_gets_ignored_inside_curly_inline',
    'test_attr_list.py::TestAttrList::test_table_td',
    'test_attr_list.py::TestAttrList::test_unclosed_quote_ignored',
    'test_autolinks.py::TestAutomaticLinks::test_email_address',
    'test_autolinks.py::TestAutomaticLinks::test_email_address_with_ampersand',
    'test_autolinks.py::TestAutomaticLinks::test_invalid_email_address_domain',
    'test_autolinks.py::TestAutomaticLinks::test_invalid_email_address_local_part',
    'test_autolinks.py::TestAutomaticLinks::test_mailto_email_address',
    'test_code.py::TestCode::test_code_comments',
    'test_code.py::TestCode::test_code_html',
    'test_code.py::TestCode::test_noname_tag',
    'test_emphasis.py::TestNotEmphasis::test_complex_emphasis_asterisk',
    'test_emphasis.py::TestNotEmphasis::test_complex_emphasis_asterisk_mid_word',
    'test_emphasis.py::TestNotEmphasis::test_complex_emphasis_smart_underscore',
    'test_emphasis.py::TestNotEmphasis::test_complex_emphasis_smart_underscore_mid_word',
    'test_emphasis.py::TestNotEmphasis::test_complex_multple_emphasis_type',
    'test_emphasis.py::TestNotEmphasis::test_complex_multple_emphasis_type_variant2',
    'test_emphasis.py::TestNotEmphasis::test_link_emphasis_inner',
    'test_emphasis.py::TestNotEmphasis::test_link_emphasis_inner_outer',
    'test_emphasis.py::TestNotEmphasis::test_link_emphasis_outer',
    'test_emphasis.py::TestNotEmphasis::test_nested_emphasis',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisk',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisk_at_end',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisk_in_text',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisks_consecutive',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisks_in_text',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisks_pairs',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisks_triples',
    'test_emphasis.py::TestNotEmphasis::test_standalone_asterisks_with_newlines',
    'test_emphasis.py::TestNotEmphasis::test_standalone_underscore_at_begin',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understore',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understore_consecutive',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understore_in_text',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understore_pairs',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understore_triples',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understores_at_begin_end',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understores_in_text',
    'test_emphasis.py::TestNotEmphasis::test_standalone_understores_with_newlines',
    'test_entities.py::TestEntities::test_decimal_entities',
    'test_entities.py::TestEntities::test_false_entities',
    'test_entities.py::TestEntities::test_hexadecimal_entities',
    'test_entities.py::TestEntities::test_named_entities',
    'test_footnotes.py::TestFootnotes::test_backlink_text',
    'test_footnotes.py::TestFootnotes::test_backlink_title',
    'test_footnotes.py::TestFootnotes::test_basic_footnote',
    'test_footnotes.py::TestFootnotes::test_duplicate_footnote_references',
    'test_footnotes.py::TestFootnotes::test_footnote_definition_without_reference',
    'test_footnotes.py::TestFootnotes::test_footnote_id_with_special_chars',
    'test_footnotes.py::TestFootnotes::test_footnote_multi_line',
    'test_footnotes.py::TestFootnotes::test_footnote_multi_line_complex',
    'test_footnotes.py::TestFootnotes::test_footnote_multi_line_lazy_indent',
    'test_footnotes.py::TestFootnotes::test_footnote_multple_complex',
    'test_footnotes.py::TestFootnotes::test_footnote_multple_complex_no_blank_line_between',
    'test_footnotes.py::TestFootnotes::test_footnote_order_by_definition',
    'test_footnotes.py::TestFootnotes::test_footnote_order_by_doc_order',
    'test_footnotes.py::TestFootnotes::test_footnote_order_tricky',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_blockquote',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_code_span',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_footnote_definition',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_html',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_link',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_within_list',
    'test_footnotes.py::TestFootnotes::test_footnote_reference_without_definition',
    'test_footnotes.py::TestFootnotes::test_footnote_references_within_loose_list',
    'test_footnotes.py::TestFootnotes::test_footnote_separator',
    'test_footnotes.py::TestFootnotes::test_multiple_footnotes',
    'test_footnotes.py::TestFootnotes::test_multiple_footnotes_multiline',
    'test_footnotes.py::TestFootnotes::test_superscript_text',
    'test_images.py::TestAdvancedImages::test_angle_with_mixed_title_quotes',
    'test_images.py::TestAdvancedImages::test_misc',
    'test_images.py::TestAdvancedImages::test_misc_blank',
    'test_images.py::TestAdvancedImages::test_misc_img',
    'test_images.py::TestAdvancedImages::test_misc_img_title',
    'test_images.py::TestAdvancedImages::test_misc_ref',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes1',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes2',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes3',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes4',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes5',
    'test_images.py::TestAdvancedImages::test_mixed_title_quotes6',
    'test_images.py::TestAdvancedImages::test_nested_round_brackets',
    'test_images.py::TestAdvancedImages::test_nested_square_brackets',
    'test_images.py::TestAdvancedImages::test_short_ref',
    'test_images.py::TestAdvancedImages::test_short_ref_in_link',
    'test_images.py::TestAdvancedImages::test_single_quote',
    'test_images.py::TestAdvancedImages::test_uneven_brackets_with_titles1',
    'test_images.py::TestAdvancedImages::test_uneven_brackets_with_titles2',
    'test_images.py::TestAdvancedImages::test_uneven_brackets_with_titles3',
    'test_images.py::TestAdvancedImages::test_uneven_brackets_with_titles4',
    'test_images.py::TestAdvancedImages::test_uneven_brackets_with_titles5',
    'test_legacy_em.py::TestLegacyEm::test_complex_emphasis_underscore',
    'test_legacy_em.py::TestLegacyEm::test_complex_emphasis_underscore_mid_word',
    'test_legacy_em.py::TestLegacyEm::test_complex_multple_underscore_type',
    'test_legacy_em.py::TestLegacyEm::test_complex_multple_underscore_type_variant2',
    'test_legacy_em.py::TestLegacyEm::test_legacy_emphasis',
    'test_legacy_em.py::TestLegacyEm::test_legacy_strong',
    'test_links.py::TestInlineLinks::test_amp_in_url',
    'test_links.py::TestInlineLinks::test_angle_with_mixed_title_quotes',
    'test_links.py::TestInlineLinks::test_angles_and_nonsense_url',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes1',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes2',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes3',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes4',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes5',
    'test_links.py::TestInlineLinks::test_mixed_title_quotes6',
    'test_links.py::TestInlineLinks::test_nested_escaped_brackets',
    'test_links.py::TestInlineLinks::test_nested_escaped_brackets_and_angles',
    'test_links.py::TestInlineLinks::test_nested_round_brackets',
    'test_links.py::TestInlineLinks::test_nested_square_brackets',
    'test_links.py::TestInlineLinks::test_nested_unescaped_brackets',
    'test_links.py::TestInlineLinks::test_nested_unescaped_brackets_and_angles',
    'test_links.py::TestInlineLinks::test_single_quote',
    'test_links.py::TestInlineLinks::test_uneven_brackets_with_titles1',
    'test_links.py::TestInlineLinks::test_uneven_brackets_with_titles2',
    'test_links.py::TestInlineLinks::test_uneven_brackets_with_titles3',
    'test_links.py::TestInlineLinks::test_uneven_brackets_with_titles4',
    'test_links.py::TestInlineLinks::test_uneven_brackets_with_titles5',
    'test_links.py::TestReferenceLinks::test_ref_link',
    'test_links.py::TestReferenceLinks::test_ref_link_angle_brackets',
    'test_links.py::TestReferenceLinks::test_ref_link_angle_brackets_no_space',
    'test_links.py::TestReferenceLinks::test_ref_link_angle_brackets_title',
    'test_links.py::TestReferenceLinks::test_ref_link_angle_brackets_title_no_space',
    'test_links.py::TestReferenceLinks::test_ref_link_multi_line',
    'test_links.py::TestReferenceLinks::test_ref_link_nested_left_bracket',
    'test_links.py::TestReferenceLinks::test_ref_link_nested_right_bracket',
    'test_links.py::TestReferenceLinks::test_ref_link_no_space',
    'test_links.py::TestReferenceLinks::test_ref_link_override',
    'test_links.py::TestReferenceLinks::test_ref_link_single_quoted_title',
    'test_links.py::TestReferenceLinks::test_ref_link_single_quoted_title_nested_quote',
    'test_links.py::TestReferenceLinks::test_ref_link_title',
    'test_links.py::TestReferenceLinks::test_ref_link_title_nested_quote',
    'test_links.py::TestReferenceLinks::test_ref_link_title_no_blank_lines',
    'test_links.py::TestReferenceLinks::test_ref_link_title_no_space',
    'test_links.py::TestReferenceLinks::test_ref_round_brackets',
    'test_links.py::TestReferenceLinks::test_reference_across_blocks',
    'test_links.py::TestReferenceLinks::test_reference_newlines',
    'test_raw_html.py::TestRawHtml::test_inline_html_angle_brackets',
    'test_raw_html.py::TestRawHtml::test_inline_html_backslashes',
    'test_raw_html.py::TestRawHtml::test_markdown_nested_in_inline_comment',
    'test_raw_html.py::TestRawHtml::test_noname_tag',
    'test_smarty.py::TestSmarty::test_basic',
    'test_smarty.py::TestSmarty::test_code_blocks',
    'test_smarty.py::TestSmarty::test_code_spans',
    'test_smarty.py::TestSmarty::test_escaped',
    'test_smarty.py::TestSmarty::test_escaped_attr',
    'test_smarty.py::TestSmarty::test_horizontal_rule',
    'test_smarty.py::TestSmarty::test_wrapping_line',
    'test_smarty.py::TestSmarty::test_years',
    'test_smarty.py::TestSmartyAngledQuotes::test_angled_quotes',
    'test_smarty.py::TestSmartyCustomSubstitutions::test_custom_substitutions',
    'test_smarty.py::TestSmartyAndToc::test_smarty_and_toc',
)
EXPECTED_NODEIDS = tuple(sorted(_NODEIDS))
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
import yaml  # noqa: F401  (imported by tests/test_apis.py)

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
    import markdown  # noqa: F401  (resolves from `source`)
    import markdown.test_tools  # noqa: F401  (the selected tests subclass its TestCase)
    if not os.path.realpath(markdown.__file__).startswith(os.path.realpath(source) + os.sep):
        raise SystemExit("markdown resolved outside the role snapshot: " + markdown.__file__)
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
        "[pytest]\naddopts =\nmarkers =\n"  # the upstream tests use no markers
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
