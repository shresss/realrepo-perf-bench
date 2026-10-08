import sqlite3

import pytest

from selectivity_work import relevant_work_profile, selective_work_ceilings


def _database(tmp_path):
    path = tmp_path / "fixture.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY);
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            issued_at TEXT NOT NULL
        );
        CREATE TABLE line_items (id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL);
        INSERT INTO customers VALUES (1), (2), (3);
        INSERT INTO invoices VALUES
            (10, 1, '2026-08-01T00:00:00'),
            (11, 1, '2026-08-31T23:59:59'),
            (12, 2, '2026-09-01T00:00:00'),
            (13, 3, '2019-01-01T00:00:00');
        INSERT INTO line_items VALUES
            (100, 10), (101, 10), (102, 11), (103, 12), (104, 13);
        """
    )
    conn.close()
    return path


def test_profile_counts_only_target_window_but_every_customer(tmp_path):
    path = _database(tmp_path)
    assert relevant_work_profile(path, "2026-08-01", "2026-09-01") == {
        "customers": 3,
        "target_month_invoices": 2,
        "target_month_line_items": 3,
        "relevant_rows": 8,
    }


def test_irrelevant_history_does_not_change_profile(tmp_path):
    path = _database(tmp_path)
    before = relevant_work_profile(path, "2026-08-01", "2026-09-01")
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO invoices VALUES (20, 2, '2018-01-01T00:00:00')")
    conn.execute("INSERT INTO line_items VALUES (200, 20)")
    conn.commit()
    conn.close()
    assert relevant_work_profile(path, "2026-08-01", "2026-09-01") == before


def test_ceilings_are_deterministic_and_relevance_scaled():
    small = selective_work_ceilings({"relevant_rows": 8})
    large = selective_work_ceilings({"relevant_rows": 80_000})
    assert small == {
        "derivation": "target-month semantic cardinalities under the pinned SQLite verifier",
        "rows": 10_008,
        "response_bytes": 7_221_248,
        "vm_steps": 500_400,
    }
    assert large["rows"] == 100_000
    assert large["response_bytes"] == 53_297_152
    assert large["vm_steps"] == 4_500_000


@pytest.mark.parametrize("value", [-1, 1.5, True, "8"])
def test_ceilings_reject_invalid_cardinality(value):
    with pytest.raises(ValueError):
        selective_work_ceilings({"relevant_rows": value})
