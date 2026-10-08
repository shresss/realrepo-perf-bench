"""Invoice pricing rules."""


def invoice_amount_cents(lines, discount_pct: int | None) -> int:
    """What an invoice is worth: its line subtotal minus the invoice-level discount.

    The discount is a whole percentage of the subtotal, taken once per invoice, and
    the discount itself is rounded down to the cent (see CHANGELOG 1.4.2).
    """
    subtotal = sum(line.quantity * line.unit_cents for line in lines)
    discount = discount_pct or 0
    return subtotal - (subtotal * discount) // 100
