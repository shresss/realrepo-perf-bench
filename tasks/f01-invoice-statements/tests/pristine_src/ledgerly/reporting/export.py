"""Writes the month-end statement export."""
import json
import os


def write_statements(path: str, month: str, statements: list[dict]) -> None:
    """Write the export as UTF-8 JSON: {"month": "YYYY-MM", "statements": [...]}.

    Compact on purpose: the file goes straight into the finance import, and at
    production size an indented copy is several times larger.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"month": month, "statements": statements}, ensure_ascii=False))
