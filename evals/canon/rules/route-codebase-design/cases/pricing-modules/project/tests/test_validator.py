import unittest

from pricing.validator import InvalidPrice, PriceValidator


class PriceValidatorTests(unittest.TestCase):
    def test_missing_currency_is_invalid(self):
        with self.assertRaises(InvalidPrice):
            PriceValidator().validate({"sku": "mug", "amount": 12.5})

    def test_negative_amount_is_invalid(self):
        with self.assertRaises(InvalidPrice):
            PriceValidator().validate({"sku": "mug", "amount": -1, "currency": "usd"})


if __name__ == "__main__":
    unittest.main()
