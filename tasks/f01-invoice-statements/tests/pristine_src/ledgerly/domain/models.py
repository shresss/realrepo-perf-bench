"""Domain objects shared by the repositories, services, and reports."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    email: str
    currency: str  # ISO 4217 code; every amount on the customer's statement is in it


@dataclass(frozen=True)
class Invoice:
    id: int
    customer_id: int
    number: str               # e.g. "INV-00042-0007"
    issued_at: str            # 'YYYY-MM-DDTHH:MM:SS'
    discount_pct: int | None  # whole percent off the subtotal; None means no discount
    status: str               # 'paid' | 'open' | 'void'


@dataclass(frozen=True)
class LineItem:
    id: int
    invoice_id: int
    product_id: int
    quantity: int
    unit_cents: int


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    sku: str
