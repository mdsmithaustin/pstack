import unittest

from checkout.seed import DEMO_CART
from checkout.summary import checkout_summary


class SummaryTest(unittest.TestCase):
    def test_counts_items(self):
        self.assertEqual(checkout_summary(DEMO_CART)["item_count"], 4)

    def test_formats_unit_prices(self):
        self.assertEqual(checkout_summary(DEMO_CART)["lines"][0]["unit_price"], "18.99 EUR")
