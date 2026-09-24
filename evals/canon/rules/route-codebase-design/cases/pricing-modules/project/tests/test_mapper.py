import unittest
from unittest import mock

from pricing.mapper import Price, PriceMapper


class PriceMapperTests(unittest.TestCase):
    def test_amount_becomes_cents_and_currency_uppercases(self):
        raw = {"sku": "mug", "amount": 12.5, "currency": "usd"}

        with mock.patch("pricing.validator.PriceValidator.validate", return_value=raw):
            price = PriceMapper().to_price(raw)

        self.assertEqual(price, Price("mug", 1250, "USD"))


if __name__ == "__main__":
    unittest.main()
