from dataclasses import dataclass
from decimal import Decimal

FREE_SHIPPING_FROM = Decimal("50.00")
FLAT_SHIPPING = Decimal("4.99")
WELCOME_RATE = Decimal("0.10")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Line:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass(frozen=True)
class Quote:
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    total: Decimal


class InvalidQuantity(ValueError):
    pass


def quote(lines: list[Line], coupon: str | None = None) -> Quote:
    for line in lines:
        if line.quantity < 1:
            raise InvalidQuantity(line.sku)
    subtotal = sum((line.unit_price * line.quantity for line in lines), Decimal("0.00"))
    discount = (subtotal * WELCOME_RATE).quantize(CENT) if coupon == "WELCOME10" else Decimal("0.00")
    discounted = subtotal - discount
    if not lines or discounted >= FREE_SHIPPING_FROM:
        shipping = Decimal("0.00")
    else:
        shipping = FLAT_SHIPPING
    return Quote(subtotal, discount, shipping, discounted + shipping)
