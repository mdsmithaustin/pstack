The four modules are one concept, a price for a SKU, split across four shallow files. The pricing service is remote but owned, so the seam sits at the transport: `HttpPriceSource` in production, `InMemoryPriceSource` in tests. Everything else lives behind `Prices.price(sku)`. The per-module tests go, replaced by tests at that interface.

<file path="pricing/prices.py">
"""A price for a SKU, read from the pricing service the catalog team runs."""
import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

PRICING_URL = "http://pricing.internal:8080"


class InvalidPrice(ValueError):
    pass


@dataclass(frozen=True)
class Price:
    sku: str
    amount_cents: int
    currency: str


class HttpPriceSource:
    def __init__(self, base_url=PRICING_URL):
        self.base_url = base_url

    def fetch(self, sku):
        with urllib.request.urlopen(f"{self.base_url}/prices/{sku}", timeout=2) as response:
            return json.loads(response.read())


class InMemoryPriceSource:
    def __init__(self, prices):
        self.prices = prices

    def fetch(self, sku):
        return dict(self.prices[sku])


class Prices:
    def __init__(self, source):
        self.source = source
        self.cached = {}

    def price(self, sku):
        if sku not in self.cached:
            self.cached[sku] = parse(self.source.fetch(sku))
        return self.cached[sku]


def parse(raw):
    missing = [key for key in ("sku", "amount", "currency") if key not in raw]
    if missing:
        raise InvalidPrice(f"price for {raw.get('sku', '?')} lacks {missing}")
    if raw["amount"] < 0:
        raise InvalidPrice(f"price for {raw['sku']} is negative")
    return Price(raw["sku"], int(Decimal(str(raw["amount"])) * 100), raw["currency"].upper())
</file>

<file path="checkout.py">
from pricing.prices import HttpPriceSource, Prices

prices = Prices(HttpPriceSource())


def cart_total_cents(lines):
    return sum(prices.price(sku).amount_cents * quantity for sku, quantity in lines)
</file>

<file path="quotes.py">
from pricing.prices import HttpPriceSource, Prices

prices = Prices(HttpPriceSource())


def quote_line(sku, quantity):
    price = prices.price(sku)
    return f"{quantity} x {sku} @ {price.amount_cents / 100:.2f} {price.currency}"
</file>

<file path="catalog_export.py">
import csv
import sys

from pricing.prices import HttpPriceSource, InvalidPrice, Prices

prices = Prices(HttpPriceSource())


def export(skus, out=sys.stdout):
    writer = csv.writer(out)
    writer.writerow(["sku", "amount_cents", "currency"])
    for sku in skus:
        try:
            price = prices.price(sku)
        except InvalidPrice:
            continue
        writer.writerow([price.sku, price.amount_cents, price.currency])
</file>

<file path="tests/test_prices.py">
import unittest

from pricing.prices import InMemoryPriceSource, InvalidPrice, Price, Prices


def prices(**table):
    return Prices(InMemoryPriceSource(table))


class PricesTests(unittest.TestCase):
    def test_price_is_in_cents_with_an_uppercase_currency(self):
        self.assertEqual(prices(mug={"sku": "mug", "amount": 12.5, "currency": "usd"}).price("mug"), Price("mug", 1250, "USD"))

    def test_missing_currency_is_invalid(self):
        with self.assertRaises(InvalidPrice):
            prices(mug={"sku": "mug", "amount": 12.5}).price("mug")

    def test_negative_amount_is_invalid(self):
        with self.assertRaises(InvalidPrice):
            prices(mug={"sku": "mug", "amount": -1, "currency": "usd"}).price("mug")

    def test_a_price_is_read_once(self):
        source = InMemoryPriceSource({"mug": {"sku": "mug", "amount": 12.5, "currency": "usd"}})
        catalog = Prices(source)
        first = catalog.price("mug")
        source.prices["mug"] = {"sku": "mug", "amount": 99, "currency": "usd"}

        self.assertEqual(catalog.price("mug"), first)


if __name__ == "__main__":
    unittest.main()
</file>

<delete path="pricing/fetcher.py"/>
<delete path="pricing/validator.py"/>
<delete path="pricing/mapper.py"/>
<delete path="pricing/cache.py"/>
<delete path="tests/test_fetcher.py"/>
<delete path="tests/test_validator.py"/>
<delete path="tests/test_mapper.py"/>
<delete path="tests/test_cache.py"/>
