"""Reporting windows."""
from datetime import date


def month_bounds(month: str) -> tuple[str, str]:
    """Return the [start, end) ISO dates of 'YYYY-MM'.

    Timestamps are stored as 'YYYY-MM-DDTHH:MM:SS' text, so comparing them with
    these dates as strings is exact: '2026-08-31T23:59:59' < '2026-09-01'.
    """
    year, mon = (int(part) for part in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + (mon == 12), mon % 12 + 1, 1)
    return start.isoformat(), end.isoformat()
