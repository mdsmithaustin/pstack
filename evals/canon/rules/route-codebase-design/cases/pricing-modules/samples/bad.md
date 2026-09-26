Callers now go through one `PricingService` that composes the fetcher, validator, mapper, and cache, so a pricing change touches one call site.

<file path="pricing/service.py">
from pricing.cache import PriceCache
from pricing.fetcher import PriceFetcher
from pricing.mapper import PriceMapper
from pricing.validator import PriceValidator


class PricingService:
    def __init__(self, fetcher=None, validator=None, mapper=None, cache=None):
        self.fetcher = fetcher or PriceFetcher()
        self.validator = validator or PriceValidator()
        self.mapper = mapper or PriceMapper()
        self.cache = cache or PriceCache()

    def price(self, sku):
        price = self.cache.get(sku)
        if price is None:
            price = self.mapper.to_price(self.validator.validate(self.fetcher.fetch(sku)))
            self.cache.put(price)
        return price
</file>

<file path="checkout.py">
from pricing.service import PricingService

pricing = PricingService()


def cart_total_cents(lines):
    return sum(pricing.price(sku).amount_cents * quantity for sku, quantity in lines)
</file>

<file path="quotes.py">
from pricing.service import PricingService

pricing = PricingService()


def quote_line(sku, quantity):
    price = pricing.price(sku)
    return f"{quantity} x {sku} @ {price.amount_cents / 100:.2f} {price.currency}"
</file>

<file path="catalog_export.py">
import csv
import sys

from pricing.service import PricingService
from pricing.validator import InvalidPrice

pricing = PricingService()


def export(skus, out=sys.stdout):
    writer = csv.writer(out)
    writer.writerow(["sku", "amount_cents", "currency"])
    for sku in skus:
        try:
            price = pricing.price(sku)
        except InvalidPrice:
            continue
        writer.writerow([price.sku, price.amount_cents, price.currency])
</file>

<file path="tests/test_service.py">
import unittest
from unittest import mock

from pricing.mapper import Price
from pricing.service import PricingService


class PricingServiceTests(unittest.TestCase):
    def test_price_runs_fetch_validate_map(self):
        fetcher = mock.Mock()
        fetcher.fetch.return_value = {"sku": "mug", "amount": 12.5, "currency": "usd"}

        price = PricingService(fetcher=fetcher).price("mug")

        fetcher.fetch.assert_called_once_with("mug")
        self.assertEqual(price, Price("mug", 1250, "USD"))


if __name__ == "__main__":
    unittest.main()
</file>
