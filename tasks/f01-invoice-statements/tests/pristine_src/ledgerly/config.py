"""Runtime settings.

Defaults are what finance expects on the month-end statements. Settings is a
plain frozen dataclass so tests and one-off scripts can override a field with
dataclasses.replace() without touching the environment.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # How an invoice's issue date is printed on a statement, e.g. "03 Aug 2026".
    date_format: str = "%d %b %Y"
    # Printed in place of the product name when a line item points at a product
    # that has since been removed from the catalog.
    unknown_product_label: str = "unknown item (deleted)"
    # Most product names ProductCatalog keeps in memory at once.
    product_cache_max: int = 256
