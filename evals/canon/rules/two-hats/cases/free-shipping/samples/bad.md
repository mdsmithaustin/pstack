One commit. It adds free shipping from $500 and folds the three copies of the rate logic into one table.

<commit message="Free shipping from $500 and clean up shipping rates">
<file path="shipping.py">
"""Shipping charges for checkout. Amounts are in cents, weights in whole kilograms."""

FREE_SHIPPING_FROM_CENTS = 50000

# zone: (up to 1 kg, up to 5 kg, up to 20 kg, per kg over 20)
RATES = {
    "domestic": (499, 899, 1599, 75),
    "canada": (999, 1899, 3499, 150),
    "international": (1999, 3999, 7999, 300),
}


def calc_shipping(order):
    zone = order["zone"]
    if zone not in RATES:
        raise ValueError(f"unknown shipping zone: {zone}")
    if order["subtotal_cents"] >= FREE_SHIPPING_FROM_CENTS:
        return 0
    light, medium, heavy, per_extra_kg = RATES[zone]
    weight = order["weight_kg"]
    if weight <= 1:
        cost = light
    elif weight <= 5:
        cost = medium
    elif weight <= 20:
        cost = heavy
    else:
        cost = heavy + (weight - 20) * per_extra_kg
    if order.get("express"):
        cost = cost * 3 // 2
    return cost
</file>
<file path="tests/test_shipping.py">
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
        self.assertEqual(calc_shipping({"zone": "domestic", "weight_kg": 12, "subtotal_cents": 64000}), 0)

    def test_express_order_just_under_threshold_pays(self):
        self.assertEqual(
            calc_shipping({"zone": "canada", "weight_kg": 2, "subtotal_cents": 49999, "express": True}),
            2848,
        )

    def test_unknown_zone_is_rejected(self):
        with self.assertRaises(ValueError):
            calc_shipping({"zone": "mars", "weight_kg": 1, "subtotal_cents": 100})


if __name__ == "__main__":
    unittest.main()
</file>
</commit>
