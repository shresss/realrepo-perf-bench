"""Connection setup and schema.

Production runs against the hosted database server; this checkout and the test
suite use SQLite with the same schema and the same SQL.
"""
import sqlite3

from .remote import connect_remote, is_remote_url

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


def connect(path: str):
    """Open the configured database with rows addressable by column name.

    Normal developer/test paths use SQLite directly.  ``metered+unix://`` paths
    use the same read-only service boundary as the hosted production deployment;
    the evaluation harness owns that service and its request accounting.
    """
    if is_remote_url(path):
        return connect_remote(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create any missing tables and indexes."""
    conn.executescript(SCHEMA)
