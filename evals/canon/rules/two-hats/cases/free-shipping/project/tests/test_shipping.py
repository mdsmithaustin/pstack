import unittest

from shipping import calc_shipping


class CalcShippingTest(unittest.TestCase):
    def test_light_domestic_parcel(self):
        self.assertEqual(calc_shipping({"zone": "domestic", "weight_kg": 1, "subtotal_cents": 2500}), 499)

    def test_heavy_canada_parcel_pays_per_extra_kilo(self):
        self.assertEqual(calc_shipping({"zone": "canada", "weight_kg": 24, "subtotal_cents": 18000}), 4099)

    def test_express_international(self):
        self.assertEqual(
            calc_shipping({"zone": "international", "weight_kg": 3, "subtotal_cents": 9000, "express": True}),
            5998,
        )

    def test_domestic_furniture_order(self):
        self.assertEqual(calc_shipping({"zone": "domestic", "weight_kg": 12, "subtotal_cents": 64000}), 1599)

    def test_unknown_zone_is_rejected(self):
        with self.assertRaises(ValueError):
            calc_shipping({"zone": "mars", "weight_kg": 1, "subtotal_cents": 100})


if __name__ == "__main__":
    unittest.main()
