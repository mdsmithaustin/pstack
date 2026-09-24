The compliance report keeps the 40-hour week from the labor agreement, so payroll gets its own threshold instead of a change to the shared one.

<file path="timesheets/hours.py">
from dataclasses import dataclass
from decimal import Decimal

REGULAR_WEEK = Decimal("40")


@dataclass(frozen=True)
class TimeCard:
    employee: str
    week: str
    hours: Decimal


def split_hours(card: TimeCard, regular_week: Decimal = REGULAR_WEEK) -> tuple[Decimal, Decimal]:
    regular = min(card.hours, regular_week)
    return regular, card.hours - regular
</file>

<file path="timesheets/payroll.py">
"""Gross pay for the payroll run."""
from decimal import Decimal

from .hours import TimeCard, split_hours

OVERTIME_MULTIPLIER = Decimal("1.5")
PAYROLL_REGULAR_WEEK = Decimal("38")


def calculate_pay(card: TimeCard, hourly_rate: Decimal) -> Decimal:
    regular, overtime = split_hours(card, PAYROLL_REGULAR_WEEK)
    gross = regular * hourly_rate + overtime * hourly_rate * OVERTIME_MULTIPLIER
    return gross.quantize(Decimal("0.01"))
</file>

<file path="tests/test_payroll.py">
import unittest
from decimal import Decimal

from timesheets.hours import TimeCard
from timesheets.payroll import calculate_pay


class CalculatePayTest(unittest.TestCase):
    def test_hours_past_thirty_eight_pay_time_and_a_half(self):
        card = TimeCard("ana", "2026-W38", Decimal("42"))

        self.assertEqual(calculate_pay(card, Decimal("20.00")), Decimal("880.00"))


if __name__ == "__main__":
    unittest.main()
</file>
