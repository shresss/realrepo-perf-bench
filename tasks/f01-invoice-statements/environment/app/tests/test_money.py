from ledgerly.domain.money import format_cents


def test_groups_thousands():
    assert format_cents(123456789, "USD") == "1,234,567.89 USD"
    assert format_cents(100000, "EUR") == "1,000.00 EUR"
    assert format_cents(99999, "GBP") == "999.99 GBP"


def test_negative_amounts():
    assert format_cents(-150075, "USD") == "-1,500.75 USD"
    assert format_cents(-5, "USD") == "-0.05 USD"


def test_zero():
    assert format_cents(0, "EUR") == "0.00 EUR"
