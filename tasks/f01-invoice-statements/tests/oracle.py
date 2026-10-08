"""Independent reference computation of the statement export.

Reads the four tables whole and does every piece of logic in Python, so it shares
no query shape and no formatting code with the original job or with any fix.
The verifier compares the agent's output on hidden databases against this.

Output contract (mirrors ledgerly 2.3.1):
  customers by id; each customer's invoices issued in [month start, next month start)
  by (issued_at, id); each invoice's items by line id; item amount = quantity *
  unit_cents before discount; invoice amount = subtotal - floor(subtotal * pct / 100)
  with NULL pct = 0; total_due = sum of non-void invoice amounts; a line whose
  product row is missing is labeled UNKNOWN_PRODUCT and still counts.
"""
import sqlite3
from datetime import date, datetime

UNKNOWN_PRODUCT = "unknown item (deleted)"
DATE_FORMAT = "%d %b %Y"


def format_cents(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{frac:02d} {currency}"


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = (int(part) for part in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start.isoformat(), end.isoformat()


def compute(db_path: str, month: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    customers = list(conn.execute("SELECT * FROM customers"))
    products = list(conn.execute("SELECT * FROM products"))
    invoices = list(conn.execute("SELECT * FROM invoices"))
    lines = list(conn.execute("SELECT * FROM line_items"))
    conn.close()

    start, end = month_bounds(month)
    product_names = {p["id"]: p["name"] for p in products}
    lines_by_invoice: dict[int, list] = {}
    for line in sorted(lines, key=lambda r: r["id"]):
        lines_by_invoice.setdefault(line["invoice_id"], []).append(line)
    invoices_by_customer: dict[int, list] = {}
    for inv in sorted(invoices, key=lambda r: (r["issued_at"], r["id"])):
        if start <= inv["issued_at"] < end:
            invoices_by_customer.setdefault(inv["customer_id"], []).append(inv)

    statements = []
    for customer in sorted(customers, key=lambda r: r["id"]):
        currency = customer["currency"]
        invoices_out = []
        total_due = 0
        for inv in invoices_by_customer.get(customer["id"], []):
            inv_lines = lines_by_invoice.get(inv["id"], [])
            items = [{"product": product_names.get(l["product_id"], UNKNOWN_PRODUCT),
                      "quantity": l["quantity"],
                      "amount": format_cents(l["quantity"] * l["unit_cents"], currency)}
                     for l in inv_lines]
            subtotal = sum(l["quantity"] * l["unit_cents"] for l in inv_lines)
            amount = subtotal - (subtotal * (inv["discount_pct"] or 0)) // 100
            issued = datetime.strptime(inv["issued_at"], "%Y-%m-%dT%H:%M:%S")
            invoices_out.append({
                "number": inv["number"],
                "issued_on": issued.strftime(DATE_FORMAT),
                "status": inv["status"],
                "line_count": len(inv_lines),
                "items": items,
                "amount": format_cents(amount, currency),
            })
            if inv["status"] != "void":
                total_due += amount
        statements.append({
            "customer_id": customer["id"],
            "name": customer["name"],
            "email": customer["email"],
            "invoice_count": len(invoices_out),
            "invoices": invoices_out,
            "total_due": format_cents(total_due, currency),
        })
    return {"month": month, "statements": statements}


if __name__ == "__main__":
    import json
    import sys

    json.dump(compute(sys.argv[1], sys.argv[2]), sys.stdout, ensure_ascii=False)
