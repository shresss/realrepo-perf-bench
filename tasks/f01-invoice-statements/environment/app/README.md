# Ledgerly

Ledgerly is our invoicing service. This repository holds the domain model, the
database access layer, and the month-end statement export that finance runs at
close: one statement per customer listing the month's invoices, their line items,
and what the customer still owes.

In production the export runs against the hosted database server over the
network. This checkout ships a SQLite fixture with the same schema and the same
SQL, so everything below runs locally with no services.

## Layout

```
ledgerly/
  config.py              Settings (date format, unknown-product label, cache size)
  report.py              the export's command line: python -m ledgerly.report
  db/
    connection.py        schema + connect()
    repositories.py      all SQL lives here; returns domain objects
  domain/
    models.py            Customer, Invoice, LineItem, Product
    money.py             cents -> "1,234.56 USD"
    pricing.py           invoice amount (subtotal minus the invoice discount)
    window.py            month -> [start, end) dates
  services/
    catalog.py           ProductCatalog: product id -> printed name
    statements.py        StatementService: builds the statements
  reporting/
    formatting.py        how dates are printed
    export.py            writes the JSON export
tests/                   pytest suite
workloads/               fixture generator and the finance job script (do not edit)
data/visible.db          a generated sample database (do not edit)
out/                     exports land here
```

## Running the export

```
python -m ledgerly.report --db data/visible.db --month 2026-08 --out out/statements.json
```

or `workloads/run_visible.sh`, which is how the finance job invokes it.

## Statement rules

- Every customer gets a statement, in customer id order, even with no invoices.
- Invoices issued in the month are listed oldest first; ties go to the lower id.
- Line items are listed in the order they were entered (line id).
- An invoice's amount is its line subtotal minus the invoice discount, taken once
  per invoice and rounded down to the cent (CHANGELOG 1.4.2). A NULL discount is 0%.
- Void invoices are listed but do not count toward `total_due`.
- A line whose product was retired from the catalog is printed as
  `Settings.unknown_product_label` and still counts toward the amount.

## Tests

```
python -m pytest tests
```

## Sample data

`data/visible.db` is generated in the image build. To make a database of a
different size or shape:

```
python workloads/gen_data.py --seed 1 --customers 1000 --out /tmp/sample.db
python workloads/gen_data.py --help      # all the knobs
```

Requirements: Python 3.12 and pytest. No third-party runtime dependencies.
