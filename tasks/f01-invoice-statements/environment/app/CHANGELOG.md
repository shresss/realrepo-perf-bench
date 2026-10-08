# Changelog

All notable changes to Ledgerly. Versions follow semver; the export's JSON shape
only changes in a minor or major release.

## 2.3.1 (2026-08-18)
- Statement export: include line items. Each invoice now carries `items`, one
  entry per line in entry order, with the product name, quantity, and the line
  amount before the invoice discount.

## 2.3.0 (2026-07-06)
- Line items whose product has been retired from the catalog no longer fail the
  export. They are listed as `unknown item (deleted)` and still count toward the
  invoice amount (finance ticket FIN-212).

## 2.2.0 (2026-05-21)
- Product catalog cache (`services/catalog.py`). Product names are looked up
  through `ProductCatalog`, which remembers names it has already resolved.
- `Settings` gains `unknown_product_label` and `product_cache_max`.

## 2.1.0 (2026-03-30)
- Void invoices are still listed on the statement but are excluded from
  `total_due`.

## 2.0.0 (2026-02-09)
- Split the single-module exporter into the `ledgerly` package (`db`, `domain`,
  `services`, `reporting`). The command line, `python -m ledgerly.report`, and
  the JSON shape are unchanged.

## 1.4.2 (2025-11-14)
- Discounts are taken once per invoice on the subtotal, and the discount is
  rounded down to the cent. Taking it per line drifted by a cent on multi-line
  invoices and did not reconcile with the ledger.
