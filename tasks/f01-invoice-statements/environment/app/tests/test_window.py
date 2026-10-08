from ledgerly.domain.window import month_bounds


def test_month_bounds():
    assert month_bounds("2026-08") == ("2026-08-01", "2026-09-01")
    assert month_bounds("2024-02") == ("2024-02-01", "2024-03-01")


def test_december_rolls_over_to_next_year():
    assert month_bounds("2025-12") == ("2025-12-01", "2026-01-01")
