The project runs plain pytest, so the scenarios stay in pytest and read as Given, When, Then.

<file path="tests/test_checkout_rules.py">
from decimal import Decimal

import pytest

from checkout.pricing import InvalidQuantity, Line, quote


def test_order_of_fifty_after_discount_ships_free():
    cart = [Line("kettle", Decimal("50.00"), 1)]

    result = quote(cart)

    assert result.shipping == Decimal("0.00")
    assert result.total == Decimal("50.00")


def test_welcome_coupon_takes_ten_percent_off_the_subtotal():
    cart = [Line("mug", Decimal("12.50"), 3)]

    result = quote(cart, coupon="WELCOME10")

    assert result.discount == Decimal("3.75")


def test_line_with_zero_quantity_is_rejected():
    cart = [Line("mug", Decimal("12.00"), 0)]

    with pytest.raises(InvalidQuantity):
        quote(cart)
</file>
