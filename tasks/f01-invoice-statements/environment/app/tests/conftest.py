"""Shared fixtures: small in-memory Ledgerly databases built from literal rows."""
import sqlite3

import pytest

from ledgerly.config import Settings
from ledgerly.db.connection import SCHEMA
from ledgerly.services.statements import StatementService


@pytest.fixture
def make_db():
    """make_db(customers=..., invoices=..., lines=..., products=...) -> an open connection.

    Rows are tuples in column order:
      customers  (id, name, email, currency)
      products   (id, name, sku)
      invoices   (id, customer_id, number, issued_at, discount_pct, status)
      lines      (id, invoice_id, product_id, quantity, unit_cents)
    """
    opened = []

    def _make(customers=(), invoices=(), lines=(), products=()):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
        conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices)
        conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", lines)
        conn.commit()
        opened.append(conn)
        return conn

    yield _make
    for conn in opened:
        conn.close()


@pytest.fixture
def build():
    """build(conn, "YYYY-MM") -> statements, with default Settings."""
    return lambda conn, month: StatementService(conn, Settings()).build(month)
