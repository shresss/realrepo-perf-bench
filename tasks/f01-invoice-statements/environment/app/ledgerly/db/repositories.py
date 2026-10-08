"""Repositories: the only modules that know the SQL.

Each repository wraps an open connection and hands back the frozen dataclasses
from ledgerly.domain.models, so services never work with raw rows.
"""
import sqlite3

from ..domain.models import Customer, Invoice, LineItem, Product


class CustomerRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def all(self) -> list[Customer]:
        """Every customer, ordered by id."""
        rows = self._conn.execute(
            "SELECT id, name, email, currency FROM customers ORDER BY id"
        ).fetchall()
        return [_customer(row) for row in rows]


class InvoiceRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def for_customer_in_window(self, customer_id: int, start: str, end: str) -> list[Invoice]:
        """A customer's invoices issued in [start, end), oldest first, ties by id."""
        rows = self._conn.execute(
            "SELECT id, customer_id, number, issued_at, discount_pct, status "
            "FROM invoices "
            "WHERE customer_id = ? AND issued_at >= ? AND issued_at < ? "
            "ORDER BY issued_at, id",
            (customer_id, start, end),
        ).fetchall()
        return [_invoice(row) for row in rows]


class LineItemRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def for_invoice(self, invoice_id: int) -> list[LineItem]:
        """An invoice's line items in the order they were entered (by id)."""
        rows = self._conn.execute(
            "SELECT id, invoice_id, product_id, quantity, unit_cents "
            "FROM line_items WHERE invoice_id = ? ORDER BY id",
            (invoice_id,),
        ).fetchall()
        return [_line_item(row) for row in rows]


class ProductRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, product_id: int) -> Product | None:
        """The product with this id, or None if it has been removed from the catalog."""
        row = self._conn.execute(
            "SELECT id, name, sku FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return _product(row) if row is not None else None


def _customer(row) -> Customer:
    return Customer(id=row["id"], name=row["name"], email=row["email"], currency=row["currency"])


def _invoice(row) -> Invoice:
    return Invoice(
        id=row["id"],
        customer_id=row["customer_id"],
        number=row["number"],
        issued_at=row["issued_at"],
        discount_pct=row["discount_pct"],
        status=row["status"],
    )


def _line_item(row) -> LineItem:
    return LineItem(
        id=row["id"],
        invoice_id=row["invoice_id"],
        product_id=row["product_id"],
        quantity=row["quantity"],
        unit_cents=row["unit_cents"],
    )


def _product(row) -> Product:
    return Product(id=row["id"], name=row["name"], sku=row["sku"])
