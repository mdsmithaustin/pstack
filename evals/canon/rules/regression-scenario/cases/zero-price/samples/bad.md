`if not cents` treated 0 like a missing price. Only `None` means unpriced.

<file path="shop/pricing.py">
def format_price(cents):
    """Price label for the product page. Items without a price yet show nothing."""
    if cents is None:
        return ""
    dollars, remainder = divmod(cents, 100)
    return f"${dollars:,}.{remainder:02d}"
</file>

<file path="tests/test_pricing.py">
import unittest

from shop.pricing import format_price


class FormatPriceTest(unittest.TestCase):
    def test_dollars_and_cents(self):
        self.assertEqual(format_price(1999), "$19.99")

    def test_thousands_separator(self):
        self.assertEqual(format_price(125000), "$1,250.00")

    def test_unpriced_item_shows_nothing(self):
        self.assertEqual(format_price(None), "")

    def test_zero_price_is_not_blank(self):
        self.assertNotEqual(format_price(0), "")


if __name__ == "__main__":
    unittest.main()
</file>
