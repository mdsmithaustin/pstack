The suite already runs pytest-bdd, so the new rules get their own feature file and reuse the shared steps.

<file path="features/pricing.feature">
Feature: Pricing
  Scenario: The WELCOME10 coupon takes ten percent off the subtotal
    Given a cart with 3 "mug" at 12.50
    When the cart is quoted with coupon "WELCOME10"
    Then the discount is 3.75

  Scenario: An unknown coupon is ignored
    Given a cart with 3 "mug" at 12.50
    When the cart is quoted with coupon "SPRING5"
    Then the discount is 0.00

  Scenario: A line with a quantity of zero is rejected
    Given a cart with 0 "mug" at 12.00
    When the cart is quoted
    Then the quote is rejected

  Scenario: An empty cart costs nothing
    Given an empty cart
    When the cart is quoted
    Then shipping is 0.00
    And the total is 0.00
</file>

<file path="tests/test_pricing.py">
from decimal import Decimal

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from checkout.pricing import InvalidQuantity, quote

scenarios("pricing.feature")


@given("an empty cart", target_fixture="cart")
def empty_cart():
    return []


@when(parsers.parse('the cart is quoted with coupon "{coupon}"'), target_fixture="result")
def quoted_with_coupon(cart, coupon):
    return quote(cart, coupon=coupon)


@when("the cart is quoted", target_fixture="result")
def quoted_or_rejected(cart):
    try:
        return quote(cart)
    except InvalidQuantity as exc:
        return exc


@then(parsers.parse("the discount is {amount}"))
def discount_is(result, amount):
    assert result.discount == Decimal(amount)


@then("the quote is rejected")
def rejected(result):
    assert isinstance(result, InvalidQuantity)
</file>
