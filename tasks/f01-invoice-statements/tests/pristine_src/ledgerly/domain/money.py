"""Money formatting. Amounts are integer cents everywhere; this is where they become text."""
import re


def format_cents(cents: int, currency: str) -> str:
    """Render integer cents as '1,234.56 USD'. Negative amounts get a leading '-'."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    grouped = re.sub(r"(\d)(?=(\d{3})+(?!\d))", r"\1,", str(whole))
    return f"{sign}{grouped}.{frac:02d} {currency}"
