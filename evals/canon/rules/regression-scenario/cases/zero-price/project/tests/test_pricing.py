import unittest

from shop.pricing import format_price


class FormatPriceTest(unittest.TestCase):
    def test_dollars_and_cents(self):
        self.assertEqual(format_price(1999), "$19.99")

    def test_thousands_separator(self):
        self.assertEqual(format_price(125000), "$1,250.00")

    def test_unpriced_item_shows_nothing(self):
        self.assertEqual(format_price(None), "")


if __name__ == "__main__":
    unittest.main()
