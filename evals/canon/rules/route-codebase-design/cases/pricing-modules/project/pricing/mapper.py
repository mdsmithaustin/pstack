from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Price:
    sku: str
    amount_cents: int
    currency: str


class PriceMapper:
    def to_price(self, raw):
        cents = int(Decimal(str(raw["amount"])) * 100)
        return Price(raw["sku"], cents, raw["currency"].upper())
