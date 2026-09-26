from decimal import Decimal

from checkout.pricing import Line, quote


def test_single_line_below_threshold_pays_flat_shipping():
    result = quote([Line("mug", Decimal("12.00"), 2)])

    assert result.total == Decimal("28.99")
