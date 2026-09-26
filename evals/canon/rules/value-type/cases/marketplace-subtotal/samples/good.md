Sellers price in different currencies, so the subtotal goes through a `Money` type that refuses to add two currencies.

<file path="checkout/money.py">
from dataclasses import dataclass


class MixedCurrencyError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    amount_cents: int
    currency: str

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise MixedCurrencyError(f"cannot add {other.currency} to {self.currency}")
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def times(self, quantity: int) -> "Money":
        return Money(self.amount_cents * quantity, self.currency)
</file>

<file path="checkout/summary.py">
from checkout.cart import Cart, Price
from checkout.money import Money


def format_price(price: Price) -> str:
    return f"{price.amount_cents / 100:.2f} {price.currency}"


def checkout_summary(cart: Cart) -> dict:
    return {
        "item_count": sum(line.quantity for line in cart.lines),
        "lines": [
            {"sku": line.sku, "seller": line.seller, "unit_price": format_price(line.price), "quantity": line.quantity}
            for line in cart.lines
        ],
        "subtotal": subtotal(cart),
    }


def subtotal(cart: Cart) -> dict[str, str]:
    totals: dict[str, Money] = {}
    for line in cart.lines:
        amount = Money(line.price.amount_cents, line.price.currency).times(line.quantity)
        totals[amount.currency] = totals[amount.currency] + amount if amount.currency in totals else amount
    return {currency: f"{money.amount_cents / 100:.2f} {currency}" for currency, money in totals.items()}
</file>
