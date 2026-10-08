"""How dates are printed on statements."""
from datetime import datetime

from ..config import Settings

STORED_TIMESTAMP = "%Y-%m-%dT%H:%M:%S"


def issued_on(issued_at: str, settings: Settings) -> str:
    """'2026-08-03T10:00:00' -> '03 Aug 2026' (Settings.date_format)."""
    return datetime.strptime(issued_at, STORED_TIMESTAMP).strftime(settings.date_format)
