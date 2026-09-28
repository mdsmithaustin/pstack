Plain pytest is simpler here, so the remaining rules are ordinary tests.

<file path="tests/test_checkout_rules.py">
from decimal import Decimal

import pytest

from checkout.pricing import InvalidQuantity, Line, quote


def test_welcome_coupon_takes_ten_percent_off_the_subtotal():
    result = quote([Line("mug", Decimal("12.50"), 3)], coupon="WELCOME10")

    assert result.discount == Decimal("3.75")


def test_line_with_zero_quantity_is_rejected():
    with pytest.raises(InvalidQuantity):
        quote([Line("mug", Decimal("12.00"), 0)])


def test_empty_cart_costs_nothing():
    assert quote([]).total == Decimal("0.00")
</file>
