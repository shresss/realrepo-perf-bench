#!/usr/bin/env python3
"""Generate a Ledgerly SQLite database: customers, a product catalog, invoices, line items.

Deterministic for a given seed. This is a test fixture generator: do not edit it.

    python workloads/gen_data.py --seed 20260801 --customers 5000 --out data/visible.db

Some line items point at retired products (ids that are no longer in the products
table), as they do in production after catalog clean-ups; see --missing-product-frac.
"""
import argparse
import os
import random
import sqlite3

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

FIRST = ["Ada", "Grace", "Linus", "Zoë", "Ólafur", "Nguyễn", "Amara", "Kenji", "Priya", "Mateo",
         "Ingrid", "Chidi", "Léa", "Yusuf", "Mei", "Sofía", "Tomás", "Aarav", "Fatima", "李"]
LAST = ["Lovelace", "Hopper", "Torvalds", "Müller", "Björk", "Trần", "Okafor", "Sato", "Nair",
        "García", "Nilsson", "Eze", "Dubois", "Khan", "Chen", "Ruiz", "Silva", "Patel", "Al-Sayed", "王"]
CURRENCIES = ["USD", "USD", "USD", "EUR", "GBP"]
PRODUCT_LINES = ["Seat license", "Support plan", "Storage overage (GB)", "API calls (per 1,000)",
                 "Onboarding", "Training session", "Data export", "Priority support", "Custom report",
                 "Consulting hours", "SSO add-on", "Audit log retention", "Sandbox environment",
                 "Premium connector", "Migration service", "Uptime SLA", "Extra workspace",
                 "Dedicated IP", "E-invoicing module", "Payroll sync"]
EDITIONS = ["Starter", "Team", "Business", "Enterprise", "Éducation"]
BILLING = ["monthly", "annual", "one-off", "usage"]
STATUSES = ["paid"] * 6 + ["open"] * 3 + ["void"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def shift_month(year: int, mon: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (mon - 1)) + delta
    return index // 12, index % 12 + 1


def days_in(year: int, mon: int) -> int:
    if mon == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        return 29
    return DAYS_IN_MONTH[mon - 1]


def random_timestamp(rng: random.Random, year: int, mon: int) -> str:
    """A random second inside the month; ~2% of the time an exact boundary second."""
    roll = rng.random()
    if roll < 0.01:
        return f"{year:04d}-{mon:02d}-01T00:00:00"
    if roll < 0.02:
        return f"{year:04d}-{mon:02d}-{days_in(year, mon):02d}T23:59:59"
    day = rng.randint(1, days_in(year, mon))
    return f"{year:04d}-{mon:02d}-{day:02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"


def product_rows(count: int) -> list[tuple]:
    """The live catalog: ids 1..count. Names repeat past 400 products; SKUs never do."""
    rows = []
    for i in range(count):
        base = PRODUCT_LINES[i % len(PRODUCT_LINES)]
        edition = EDITIONS[(i // len(PRODUCT_LINES)) % len(EDITIONS)]
        billing = BILLING[(i // (len(PRODUCT_LINES) * len(EDITIONS))) % len(BILLING)]
        rows.append((i + 1, f"{base} ({edition}, {billing})", f"SKU-{i + 1:06d}"))
    return rows


def invoices_for_customer(rng: random.Random, args) -> int:
    roll = rng.random()
    if roll < args.zero_frac:
        return 0
    if roll < args.zero_frac + args.tail_frac:
        return rng.randint(args.tail_min, args.tail_max)
    return rng.randint(args.min_inv, args.max_inv)


def pick_product(rng: random.Random, args, retired: int) -> int:
    """A live product id, or (missing_product_frac of the time) a retired one above the catalog."""
    if rng.random() < args.missing_product_frac:
        return args.products + rng.randint(1, retired)
    return rng.randint(1, args.products)


def generate(args) -> dict:
    rng = random.Random(args.seed)
    year, mon = (int(part) for part in args.month.split("-"))
    retired = max(1, args.products // 10)
    products = product_rows(args.products)
    customers, invoices, lines = [], [], []
    invoice_id = 0
    line_id = 0
    for cid in range(1, args.customers + 1):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        customers.append((cid, name, f"customer{cid}@example.com", rng.choice(CURRENCIES)))
        for seq in range(1, invoices_for_customer(rng, args) + 1):
            invoice_id += 1
            roll = rng.random()
            if roll < 0.70:
                y, m = year, mon
            elif roll < 0.85:
                y, m = shift_month(year, mon, -1)
            else:
                y, m = shift_month(year, mon, +1)
            discount = None if rng.random() < 0.40 else rng.randint(0, 30)
            invoices.append((invoice_id, cid, f"INV-{cid:05d}-{seq:04d}", random_timestamp(rng, y, m),
                             discount, rng.choice(STATUSES)))
            n_lines = 0 if rng.random() < args.empty_inv_frac else rng.randint(1, 8)
            for _ in range(n_lines):
                line_id += 1
                row = (line_id, invoice_id, pick_product(rng, args, retired),
                       rng.randint(1, 20), rng.randint(100, 50000))
                lines.append(row)
                if rng.random() < args.dup_frac:
                    line_id += 1
                    lines.append((line_id,) + row[1:])

    if os.path.exists(args.out):
        os.remove(args.out)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    conn = sqlite3.connect(args.out)
    conn.executescript(SCHEMA)
    with conn:
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
        conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices)
        conn.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?)", lines)
    conn.close()
    return {"customers": len(customers), "products": len(products), "invoices": len(invoices),
            "line_items": len(lines)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--customers", type=int, default=5000)
    parser.add_argument("--out", required=True)
    parser.add_argument("--month", default="2026-08", help="the month most invoices fall in")
    parser.add_argument("--zero-frac", type=float, default=0.10, help="share of customers with no invoices")
    parser.add_argument("--min-inv", type=int, default=5)
    parser.add_argument("--max-inv", type=int, default=15)
    parser.add_argument("--tail-frac", type=float, default=0.0, help="share of customers with very many invoices")
    parser.add_argument("--tail-min", type=int, default=200)
    parser.add_argument("--tail-max", type=int, default=1500)
    parser.add_argument("--dup-frac", type=float, default=0.05, help="chance a line item is duplicated")
    parser.add_argument("--empty-inv-frac", type=float, default=0.05, help="share of invoices with no lines")
    parser.add_argument("--products", type=int, default=400, help="size of the live product catalog")
    parser.add_argument("--missing-product-frac", type=float, default=0.02,
                        help="share of line items whose product has been retired from the catalog")
    args = parser.parse_args(argv)
    if args.products < 1:
        parser.error("--products must be at least 1")
    return args


if __name__ == "__main__":
    counts = generate(parse_args())
    print(counts)
