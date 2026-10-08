"""Month-end statements: what each customer was invoiced in a month and what they owe."""
import sqlite3

from ..config import Settings
from ..db.repositories import (
    CustomerRepository,
    InvoiceRepository,
    LineItemRepository,
    ProductRepository,
)
from ..domain.models import Customer, Invoice, LineItem
from ..domain.money import format_cents
from ..domain.pricing import invoice_amount_cents
from ..domain.window import month_bounds
from ..reporting import formatting
from .catalog import ProductCatalog


class StatementService:
    """Builds one statement per customer, in customer id order.

    A statement lists the customer's invoices issued in the month, oldest first
    (ties by invoice id), each with its line items in entry order. Every customer
    gets a statement, including customers with no invoices that month. Void
    invoices are listed but do not count toward total_due.

    The month's invoices and line items (with product names) are read in one
    query each and grouped in memory, so the number of queries does not grow
    with the number of customers, invoices, or lines.
    """

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.settings = settings
        self.customers = CustomerRepository(conn)
        self.invoices = InvoiceRepository(conn)
        self.line_items = LineItemRepository(conn)
        self.catalog = ProductCatalog(ProductRepository(conn), settings)

    def build(self, month: str) -> list[dict]:
        """Statements for 'YYYY-MM'."""
        start, end = month_bounds(month)
        invoices_by_customer = self.invoices.in_window(start, end)
        lines_by_invoice = self.line_items.for_invoices_in_window(start, end)
        statements = []
        for customer in self.customers.all():
            invoices = invoices_by_customer.get(customer.id, [])
            statements.append(self._statement_for(customer, invoices, lines_by_invoice))
        return statements

    def _statement_for(
        self,
        customer: Customer,
        invoices: list[Invoice],
        lines_by_invoice: dict[int, list[tuple[LineItem, str | None]]],
    ) -> dict:
        invoices_out = []
        total_due = 0
        for invoice in invoices:
            entries = lines_by_invoice.get(invoice.id, [])
            lines = [line for line, _ in entries]
            items = [self._item_for(line, name, customer.currency) for line, name in entries]
            amount = invoice_amount_cents(lines, invoice.discount_pct)
            invoices_out.append(
                {
                    "number": invoice.number,
                    "issued_on": formatting.issued_on(invoice.issued_at, self.settings),
                    "status": invoice.status,
                    "line_count": len(lines),
                    "items": items,
                    "amount": format_cents(amount, customer.currency),
                }
            )
            if invoice.status != "void":
                total_due += amount
        return {
            "customer_id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "invoice_count": len(invoices_out),
            "invoices": invoices_out,
            "total_due": format_cents(total_due, customer.currency),
        }

    def _item_for(self, line: LineItem, product_name: str | None, currency: str) -> dict:
        # Line amounts are shown before the invoice-level discount.
        if product_name is None:
            product_name = self.settings.unknown_product_label
        return {
            "product": product_name,
            "quantity": line.quantity,
            "amount": format_cents(line.quantity * line.unit_cents, currency),
        }
