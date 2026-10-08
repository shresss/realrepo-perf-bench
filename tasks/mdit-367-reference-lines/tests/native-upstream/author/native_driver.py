"""Protected native assertions extracted unchanged from pinned upstream source.

The wrapper only selects data/instantiates upstream assertion functions. It uses
stdlib fixture decoding, so candidate fixture utilities do not own assertion data.
"""
import ast
import json
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent


def _function(filename, name):
    module = ast.parse((HERE / filename).read_text())
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    scope = {"MarkdownIt": MarkdownIt}
    exec(compile(ast.Module(body=[function], type_ignores=[]), filename, "exec"), scope)
    return scope[name]


_definition_assertion = _function("test_references.py", "test_ref_definitions")
_spec_assertion = _function("test_spec.py", "test_spec")
_extra_assertion = _function("test_fixtures.py", "test_commonmark_extras")
_spec_rows = [row for row in json.loads((HERE / "commonmark.json").read_text()) if row["section"] in ("Link reference definitions", "Links", "Images")]


def _extras():
    # The same three-dot-line framing as the upstream fixture format; this is
    # authored stdlib decoding, not candidate markdown_it.utils.read_fixture_file.
    lines = (HERE / "commonmark_extras.md").read_text().splitlines(keepends=True)
    result = []
    separators = [i for i, line in enumerate(lines) if line.rstrip() == "."]
    assert len(separators) % 3 == 0
    for begin, middle, end in zip(separators[::3], separators[1::3], separators[2::3]):
        title = lines[begin - 1].strip()
        if title.startswith(("Reference labels:", "Reference can be", "Escape character in link reference title")):
            result.append((begin, title, "".join(lines[begin + 1:middle]), "".join(lines[middle + 1:end])))
    assert len(result) == 4
    return result


def test_reference_definitions():
    _definition_assertion()


@pytest.mark.parametrize("entry", _spec_rows, ids=[str(row["example"]) for row in _spec_rows])
def test_commonmark_reference(entry):
    _spec_assertion(entry)


@pytest.mark.parametrize("row", _extras(), ids=[str(row[0]) for row in _extras()])
def test_reference_extras(row):
    _extra_assertion(*row)
