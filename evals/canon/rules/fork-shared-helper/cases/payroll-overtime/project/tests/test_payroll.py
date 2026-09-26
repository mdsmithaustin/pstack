import unittest
from decimal import Decimal

from timesheets.hours import TimeCard
from timesheets.payroll import calculate_pay


class CalculatePayTest(unittest.TestCase):
    def test_hours_past_the_regular_week_pay_time_and_a_half(self):
        card = TimeCard("ana", "2026-W38", Decimal("42"))

        self.assertEqual(calculate_pay(card, Decimal("20.00")), Decimal("860.00"))


if __name__ == "__main__":
    unittest.main()
