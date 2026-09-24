I added pytest-bdd so the rules live in a feature file.

<file path="pyproject.toml">
[project]
name = "checkout"
version = "0.4.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-bdd>=7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
</file>

<file path="tests/features/checkout.feature">
Feature: Checkout pricing
  Scenario: Free shipping from fifty
    Given a cart with one kettle at 50.00
    When I request a quote
    Then shipping is 0.00
</file>

<file path="tests/test_checkout_steps.py">
from decimal import Decimal

from pytest_bdd import given, scenarios, then, when

from checkout.pricing import Line, quote

scenarios("features/checkout.feature")


@given("a cart with one kettle at 50.00", target_fixture="cart")
def cart():
    return [Line("kettle", Decimal("50.00"), 1)]


@when("I request a quote", target_fixture="result")
def result(cart):
    return quote(cart)


@then("shipping is 0.00")
def free_shipping(result):
    assert result.shipping == Decimal("0.00")
</file>
