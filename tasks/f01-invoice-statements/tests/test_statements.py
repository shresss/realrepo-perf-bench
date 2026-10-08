"""Verifier correctness suite: the visible tests plus the edge cases a naive fix breaks.

Runs against the agent's tree. Every test goes through the same public surface the
visible suite uses (StatementService(conn, Settings()).build, format_cents,
month_bounds, and the CLI's main), so any internal refactor is fine.
"""
import json
import os
import sqlite3
import sys

# Inside the container the package lives at /app. Our QC scripts run this suite on a
# laptop by setting LEDGERLY_APP; Harbor never sets it.
sys.path.insert(0, os.environ.get("LEDGERLY_APP", "/app"))

from ledgerly.config import Settings  # noqa: E402
from ledgerly.domain.money import format_cents  # noqa: E402
from ledgerly.domain.window import month_bounds  # noqa: E402
from ledgerly.report import main  # noqa: E402
from ledgerly.services.statements import StatementService  # noqa: E402

# Identical to ledgerly/db/connection.py and workloads/gen_data.py in the task image.
SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    email     TEXT NOT NULL,
    currency  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    sku   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    number        TEXT NOT NULL,
    issued_at     TEXT NOT NULL,          -- ISO 8601, 'YYYY-MM-DDTHH:MM:SS'
    discount_pct  INTEGER,                -- NULL means no discount
    status        TEXT NOT NULL           -- 'paid' | 'open' | 'void'
);
CREATE TABLE IF NOT EXISTS line_items (
    id           INTEGER PRIMARY KEY,
    invoice_id   INTEGER NOT NULL REFERENCES invoices(id),
    product_id   INTEGER NOT NULL,        -- no FK: retired products are deleted, old lines keep the id
    quantity     INTEGER NOT NULL,
    unit_cents   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id, issued_at);
CREATE INDEX IF NOT EXISTS idx_line_items_invoice ON line_items(invoice_id);
"""

UNKNOWN = "unknown item (deleted)"
PRODUCTS = [
    (1, "Consulting hours", "SKU-000001"),
    (2, "Seat license", "SKU-000002"),
    (3, "Support plan", "SKU-000003"),
    (4, "Onboarding", "SKU-000004"),
    (5, "API calls (per 1,000)", "SKU-000005"),
]


def make_db(customers=(), invoices=(), lines=(), products=PRODUCTS):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
    conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)
    conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices)
    conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", lines)
    conn.commit()
    return conn


def build(conn, month):
    return StatementService(conn, Settings()).build(month)


# ---- the visible tests, repeated so the verifier does not depend on /app/tests ----

def test_basic_totals_and_formatting():
    conn = make_db(
        [(1, "Ada Lovelace", "ada@example.com", "USD")],
        [(10, 1, "INV-00001-0001", "2026-08-03T10:00:00", None, "paid"),
         (11, 1, "INV-00001-0002", "2026-08-20T09:30:00", 10, "open")],
        [(100, 10, 1, 2, 15000), (101, 11, 2, 3, 4000), (102, 11, 3, 1, 123456)],
    )
    [stmt] = build(conn, "2026-08")
    # subtotal 135,456 cents; 10% off floors to 121,911 -> 1,219.11
    assert [inv["amount"] for inv in stmt["invoices"]] == ["300.00 USD", "1,219.11 USD"]
    assert stmt["invoices"][0]["issued_on"] == "03 Aug 2026"
    assert stmt["invoices"][1]["items"] == [
        {"product": "Seat license", "quantity": 3, "amount": "120.00 USD"},
        {"product": "Support plan", "quantity": 1, "amount": "1,234.56 USD"},
    ]
    assert stmt["total_due"] == "1,519.11 USD"


def test_only_invoices_issued_in_the_month_are_listed():
    conn = make_db(
        [(1, "Grace Hopper", "grace@example.com", "EUR")],
        [(1, 1, "INV-00001-0001", "2026-07-31T23:59:59", None, "paid"),
         (2, 1, "INV-00001-0002", "2026-08-15T12:00:00", None, "paid"),
         (3, 1, "INV-00001-0003", "2026-09-01T00:00:00", None, "paid")],
        [(1, 1, 4, 1, 100), (2, 2, 4, 1, 200), (3, 3, 4, 1, 300)],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0002"]
    assert stmt["total_due"] == "2.00 EUR"


def test_void_invoices_are_listed_but_not_owed():
    conn = make_db(
        [(1, "Linus Torvalds", "linus@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-02T08:00:00", None, "void"),
         (2, 1, "INV-00001-0002", "2026-08-03T08:00:00", None, "open")],
        [(1, 1, 2, 1, 5000), (2, 2, 2, 1, 7000)],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["status"] for inv in stmt["invoices"]] == ["void", "open"]
    assert stmt["invoices"][0]["amount"] == "50.00 USD"
    assert stmt["total_due"] == "70.00 USD"


def test_invoices_are_ordered_by_issue_time_then_id():
    conn = make_db(
        [(1, "Amara Okafor", "amara@example.com", "GBP")],
        [(3, 1, "INV-00001-0003", "2026-08-10T00:00:00", None, "paid"),
         (1, 1, "INV-00001-0001", "2026-08-10T00:00:00", None, "paid"),
         (2, 1, "INV-00001-0002", "2026-08-09T23:00:00", None, "paid")],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0002", "INV-00001-0001", "INV-00001-0003"]


def test_items_are_listed_in_line_order():
    conn = make_db(
        [(1, "Kenji Sato", "kenji@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid")],
        [(7, 1, 4, 1, 100), (3, 1, 3, 2, 250), (5, 1, 1, 1, 999)],
    )
    [stmt] = build(conn, "2026-08")
    assert [item["product"] for item in stmt["invoices"][0]["items"]] == [
        "Support plan", "Consulting hours", "Onboarding"]


def test_money_formatting():
    assert format_cents(123456789, "USD") == "1,234,567.89 USD"
    assert format_cents(-150075, "USD") == "-1,500.75 USD"
    assert format_cents(0, "EUR") == "0.00 EUR"


def test_month_bounds():
    assert month_bounds("2026-08") == ("2026-08-01", "2026-09-01")
    assert month_bounds("2025-12") == ("2025-12-01", "2026-01-01")


# ---- the edge cases a naive set-based rewrite breaks ----

def test_customer_with_no_invoices_is_still_listed():
    conn = make_db(
        [(1, "Zoë Müller", "z@example.com", "EUR"), (2, "Kenji Sato", "k@example.com", "USD")],
        [(1, 2, "INV-00002-0001", "2026-08-05T00:00:00", None, "paid")],
        [(1, 1, 4, 1, 100)],
    )
    stmts = build(conn, "2026-08")
    assert [s["customer_id"] for s in stmts] == [1, 2]
    assert stmts[0] == {"customer_id": 1, "name": "Zoë Müller", "email": "z@example.com",
                        "invoice_count": 0, "invoices": [], "total_due": "0.00 EUR"}


def test_invoice_with_no_line_items_is_listed_with_zero_amount():
    conn = make_db(
        [(1, "Priya Nair", "p@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", 15, "open"),
         (2, 1, "INV-00001-0002", "2026-08-06T00:00:00", None, "open")],
        [(1, 2, 5, 1, 999)],
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["invoice_count"] == 2
    assert stmt["invoices"][0] == {"number": "INV-00001-0001", "issued_on": "05 Aug 2026", "status": "open",
                                   "line_count": 0, "items": [], "amount": "0.00 USD"}
    assert stmt["total_due"] == "9.99 USD"


def test_discount_is_applied_once_per_invoice_not_per_line():
    # subtotal 333 + 333 + 335 = 1001; 10% off the invoice -> 1001 - 100 = 901.
    # Per-line discounting (300 + 300 + 302) would give 902; SUM over a join would double count.
    conn = make_db(
        [(1, "Mateo García", "m@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", 10, "paid")],
        [(1, 1, 1, 1, 333), (2, 1, 2, 1, 333), (3, 1, 3, 1, 335)],
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["invoices"][0]["amount"] == "9.01 USD"
    assert [item["amount"] for item in stmt["invoices"][0]["items"]] == ["3.33 USD", "3.33 USD", "3.35 USD"]
    assert stmt["total_due"] == "9.01 USD"


def test_null_discount_means_no_discount():
    conn = make_db(
        [(1, "Ingrid Nilsson", "i@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid"),
         (2, 1, "INV-00001-0002", "2026-08-06T00:00:00", 0, "paid")],
        [(1, 1, 2, 2, 500), (2, 2, 2, 2, 500)],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["amount"] for inv in stmt["invoices"]] == ["10.00 USD", "10.00 USD"]


def test_duplicate_line_rows_both_count():
    conn = make_db(
        [(1, "Chidi Eze", "c@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid")],
        [(1, 1, 2, 1, 5000), (2, 1, 2, 1, 5000)],
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["invoices"][0]["line_count"] == 2
    assert stmt["invoices"][0]["items"] == [{"product": "Seat license", "quantity": 1, "amount": "50.00 USD"}] * 2
    assert stmt["invoices"][0]["amount"] == "100.00 USD"


def test_month_boundaries_are_inclusive_start_exclusive_end():
    conn = make_db(
        [(1, "Léa Dubois", "l@example.com", "EUR")],
        [(1, 1, "INV-00001-0001", "2026-08-01T00:00:00", None, "paid"),
         (2, 1, "INV-00001-0002", "2026-08-31T23:59:59", None, "paid"),
         (3, 1, "INV-00001-0003", "2026-09-01T00:00:00", None, "paid"),
         (4, 1, "INV-00001-0004", "2026-07-31T23:59:59", None, "paid")],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0001", "INV-00001-0002"]


def test_december_rolls_over_to_next_year():
    conn = make_db(
        [(1, "Yusuf Khan", "y@example.com", "GBP")],
        [(1, 1, "INV-00001-0001", "2025-12-31T23:59:59", None, "paid"),
         (2, 1, "INV-00001-0002", "2026-01-01T00:00:00", None, "paid")],
    )
    [stmt] = build(conn, "2025-12")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0001"]


def test_customers_are_ordered_by_id_regardless_of_insert_order():
    conn = make_db(
        [(3, "王 李", "w@example.com", "USD"), (1, "Sofía Ruiz", "s@example.com", "USD"),
         (2, "Aarav Patel", "a@example.com", "USD")],
    )
    stmts = build(conn, "2026-08")
    assert [s["customer_id"] for s in stmts] == [1, 2, 3]
    assert stmts[2]["name"] == "王 李"


def test_line_with_deleted_product_still_counts():
    # Product 9 was retired from the catalog; the line keeps its id and still bills.
    conn = make_db(
        [(1, "Tomás Silva", "t@example.com", "EUR")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", 20, "open")],
        [(1, 1, 2, 1, 1000), (2, 1, 9, 2, 1500), (3, 1, 3, 1, 500)],
    )
    [stmt] = build(conn, "2026-08")
    invoice = stmt["invoices"][0]
    assert invoice["line_count"] == 3
    assert invoice["items"] == [
        {"product": "Seat license", "quantity": 1, "amount": "10.00 EUR"},
        {"product": UNKNOWN, "quantity": 2, "amount": "30.00 EUR"},
        {"product": "Support plan", "quantity": 1, "amount": "5.00 EUR"},
    ]
    assert invoice["amount"] == "36.00 EUR"      # 4,500 - 20% = 3,600
    assert stmt["total_due"] == "36.00 EUR"


def test_invoice_whose_only_product_is_deleted_is_still_listed():
    conn = make_db(
        [(1, "Ólafur Björk", "o@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid")],
        [(1, 1, 404, 3, 700)],
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["invoices"][0]["items"] == [{"product": UNKNOWN, "quantity": 3, "amount": "21.00 USD"}]
    assert stmt["total_due"] == "21.00 USD"


def test_same_product_on_several_invoices_keeps_its_name():
    conn = make_db(
        [(1, "Nguyễn Trần", "n@example.com", "USD"), (2, "Fatima Al-Sayed", "f@example.com", "GBP")],
        [(1, 1, "INV-00001-0001", "2026-08-01T09:00:00", None, "paid"),
         (2, 2, "INV-00002-0001", "2026-08-02T09:00:00", None, "paid"),
         (3, 1, "INV-00001-0002", "2026-08-03T09:00:00", None, "paid")],
        [(1, 1, 5, 1, 100), (2, 2, 5, 2, 100), (3, 3, 5, 3, 100), (4, 3, 1, 1, 100)],
    )
    stmts = build(conn, "2026-08")
    names = [item["product"] for s in stmts for inv in s["invoices"] for item in inv["items"]]
    assert names == ["API calls (per 1,000)", "API calls (per 1,000)", "Consulting hours", "API calls (per 1,000)"]
    assert stmts[1]["invoices"][0]["items"][0]["amount"] == "2.00 GBP"


def test_items_follow_line_id_not_product_or_insert_order():
    conn = make_db(
        [(1, "Sofía Ruiz", "s@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid")],
        [(30, 1, 1, 1, 100), (10, 1, 4, 1, 200), (20, 1, 9, 1, 300), (40, 1, 2, 1, 400)],
    )
    [stmt] = build(conn, "2026-08")
    assert [item["product"] for item in stmt["invoices"][0]["items"]] == [
        "Onboarding", UNKNOWN, "Consulting hours", "Seat license"]


def test_large_amounts_group_thousands():
    conn = make_db(
        [(1, "Fatima Al-Sayed", "f@example.com", "USD")],
        [(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "open")],
        [(1, 1, 1, 20, 50000), (2, 1, 1, 200, 50000)],
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["invoices"][0]["items"][1]["amount"] == "100,000.00 USD"
    assert stmt["total_due"] == "110,000.00 USD"


def test_cli_writes_json_export(tmp_path):
    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO customers VALUES (1, 'Mei Chen', 'mei@example.com', 'USD')")
    conn.execute("INSERT INTO customers VALUES (2, 'Linus Torvalds', 'linus@example.com', 'EUR')")
    conn.execute("INSERT INTO products VALUES (1, 'API calls (per 1,000)', 'SKU-000001')")
    conn.execute("INSERT INTO invoices VALUES (1, 1, 'INV-00001-0001', '2026-08-01T00:00:00', 5, 'paid')")
    conn.execute("INSERT INTO line_items VALUES (1, 1, 1, 10, 1000)")
    conn.execute("INSERT INTO line_items VALUES (2, 1, 77, 1, 250)")
    conn.commit()
    conn.close()
    out = tmp_path / "out" / "statements.json"
    assert main(["--db", str(db_path), "--month", "2026-08", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"month": "2026-08", "statements": [
        {"customer_id": 1, "name": "Mei Chen", "email": "mei@example.com", "invoice_count": 1,
         "invoices": [{"number": "INV-00001-0001", "issued_on": "01 Aug 2026", "status": "paid", "line_count": 2,
                       "items": [{"product": "API calls (per 1,000)", "quantity": 10, "amount": "100.00 USD"},
                                 {"product": UNKNOWN, "quantity": 1, "amount": "2.50 USD"}],
                       "amount": "97.38 USD"}],
         "total_due": "97.38 USD"},
        {"customer_id": 2, "name": "Linus Torvalds", "email": "linus@example.com", "invoice_count": 0,
         "invoices": [], "total_due": "0.00 EUR"}]}
