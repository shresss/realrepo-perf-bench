from io import StringIO

import pytest

from exact_json import first_json_difference, load_exact_json


def test_exact_json_rejects_python_numeric_type_aliases():
    assert first_json_difference({"id": 1}, {"id": True}) is not None
    assert first_json_difference({"id": 1}, {"id": 1.0}) is not None
    assert first_json_difference({"ok": False}, {"ok": 0}) is not None


def test_exact_json_accepts_only_matching_structure_types_and_values():
    value = {"rows": [{"id": 1, "name": "Ada"}], "empty": [], "none": None}
    assert first_json_difference(value, value) is None
    assert first_json_difference(value, {**value, "extra": 1}) is not None
    assert first_json_difference(value, {**value, "rows": []}) is not None


def test_strict_parser_rejects_duplicate_keys_and_nonstandard_numbers():
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_exact_json(StringIO('{"month":"wrong","month":"2026-08"}'))
    for token in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match="non-standard JSON constant"):
            load_exact_json(StringIO('{"value":' + token + '}'))


def test_strict_parser_accepts_standard_nested_json():
    value = {"month": "2026-08", "rows": [{"id": 1}], "ok": True}
    assert load_exact_json(StringIO('{"month":"2026-08","rows":[{"id":1}],"ok":true}')) == value
