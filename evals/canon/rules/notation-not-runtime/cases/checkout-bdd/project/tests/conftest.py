from decimal import Decimal

from pytest_bdd import given, parsers, then, when

from checkout.pricing import Line, quote


@given(parsers.parse('a cart with {quantity:d} "{sku}" at {price}'), target_fixture="cart")
def cart(quantity, sku, price):
    return [Line(sku, Decimal(price), quantity)]


@when("the cart is quoted", target_fixture="result")
def quoted(cart):
    return quote(cart)


@then(parsers.parse("shipping is {amount}"))
def shipping_is(result, amount):
    assert result.shipping == Decimal(amount)


@then(parsers.parse("the total is {amount}"))
def total_is(result, amount):
    assert result.total == Decimal(amount)
