"""StatementService: totals, the month window, void handling, and ordering."""

PRODUCTS = [
    (1, "Consulting hours", "SKU-000001"),
    (2, "Seat license", "SKU-000002"),
    (3, "Support plan", "SKU-000003"),
    (4, "Onboarding", "SKU-000004"),
]


def test_basic_totals_and_formatting(make_db, build):
    conn = make_db(
        customers=[(1, "Ada Lovelace", "ada@example.com", "USD")],
        products=PRODUCTS,
        invoices=[(10, 1, "INV-00001-0001", "2026-08-03T10:00:00", None, "paid"),
                  (11, 1, "INV-00001-0002", "2026-08-20T09:30:00", 10, "open")],
        lines=[(100, 10, 1, 2, 15000),      # 300.00
               (101, 11, 2, 3, 4000),       # 120.00
               (102, 11, 3, 1, 123456)],    # 1,234.56 -> subtotal 1,354.56; 10% off -> 1,219.11
    )
    [stmt] = build(conn, "2026-08")
    assert stmt["customer_id"] == 1
    assert stmt["invoice_count"] == 2
    assert [inv["amount"] for inv in stmt["invoices"]] == ["300.00 USD", "1,219.11 USD"]
    assert stmt["invoices"][0]["issued_on"] == "03 Aug 2026"
    assert stmt["invoices"][1]["line_count"] == 2
    assert stmt["invoices"][1]["items"] == [
        {"product": "Seat license", "quantity": 3, "amount": "120.00 USD"},
        {"product": "Support plan", "quantity": 1, "amount": "1,234.56 USD"},
    ]
    assert stmt["total_due"] == "1,519.11 USD"


def test_only_invoices_issued_in_the_month_are_listed(make_db, build):
    conn = make_db(
        customers=[(1, "Grace Hopper", "grace@example.com", "EUR")],
        products=PRODUCTS,
        invoices=[(1, 1, "INV-00001-0001", "2026-07-31T23:59:59", None, "paid"),
                  (2, 1, "INV-00001-0002", "2026-08-15T12:00:00", None, "paid"),
                  (3, 1, "INV-00001-0003", "2026-09-01T00:00:00", None, "paid")],
        lines=[(1, 1, 4, 1, 100), (2, 2, 4, 1, 200), (3, 3, 4, 1, 300)],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0002"]
    assert stmt["total_due"] == "2.00 EUR"


def test_void_invoices_are_listed_but_not_owed(make_db, build):
    conn = make_db(
        customers=[(1, "Linus Torvalds", "linus@example.com", "USD")],
        products=PRODUCTS,
        invoices=[(1, 1, "INV-00001-0001", "2026-08-02T08:00:00", None, "void"),
                  (2, 1, "INV-00001-0002", "2026-08-03T08:00:00", None, "open")],
        lines=[(1, 1, 2, 1, 5000), (2, 2, 2, 1, 7000)],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["status"] for inv in stmt["invoices"]] == ["void", "open"]
    assert stmt["invoices"][0]["amount"] == "50.00 USD"
    assert stmt["total_due"] == "70.00 USD"


def test_invoices_are_ordered_by_issue_time_then_id(make_db, build):
    conn = make_db(
        customers=[(1, "Amara Okafor", "amara@example.com", "GBP")],
        invoices=[(3, 1, "INV-00001-0003", "2026-08-10T00:00:00", None, "paid"),
                  (1, 1, "INV-00001-0001", "2026-08-10T00:00:00", None, "paid"),
                  (2, 1, "INV-00001-0002", "2026-08-09T23:00:00", None, "paid")],
    )
    [stmt] = build(conn, "2026-08")
    assert [inv["number"] for inv in stmt["invoices"]] == ["INV-00001-0002", "INV-00001-0001", "INV-00001-0003"]


def test_items_are_listed_in_line_order(make_db, build):
    conn = make_db(
        customers=[(1, "Kenji Sato", "kenji@example.com", "USD")],
        products=PRODUCTS,
        invoices=[(1, 1, "INV-00001-0001", "2026-08-05T00:00:00", None, "paid")],
        lines=[(7, 1, 4, 1, 100), (3, 1, 3, 2, 250), (5, 1, 1, 1, 999)],
    )
    [stmt] = build(conn, "2026-08")
    assert [item["product"] for item in stmt["invoices"][0]["items"]] == [
        "Support plan", "Consulting hours", "Onboarding"]
    assert [item["amount"] for item in stmt["invoices"][0]["items"]] == ["5.00 USD", "9.99 USD", "1.00 USD"]
