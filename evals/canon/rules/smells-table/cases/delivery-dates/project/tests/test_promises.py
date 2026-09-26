import unittest
from datetime import date

from shipping.promises import carrier_deadline, checkout_promise


class DeliveryDateTest(unittest.TestCase):
    def test_friday_order_with_one_warehouse_day_promises_tuesday(self):
        self.assertEqual(checkout_promise(date(2026, 9, 25), 1), date(2026, 9, 29))

    def test_carrier_deadline_skips_the_weekend(self):
        self.assertEqual(carrier_deadline(date(2026, 9, 25), 0), date(2026, 9, 28))


if __name__ == "__main__":
    unittest.main()
