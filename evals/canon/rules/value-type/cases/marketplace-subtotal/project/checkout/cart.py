from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    amount_cents: int
    currency: str


@dataclass(frozen=True)
class CartLine:
    sku: str
    seller: str
    price: Price
    quantity: int


@dataclass(frozen=True)
class Cart:
    lines: tuple[CartLine, ...]
