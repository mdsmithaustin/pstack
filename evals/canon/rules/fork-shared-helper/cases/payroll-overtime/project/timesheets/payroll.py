"""Gross pay for the payroll run."""
from decimal import Decimal

from .hours import TimeCard, split_hours

OVERTIME_MULTIPLIER = Decimal("1.5")


def calculate_pay(card: TimeCard, hourly_rate: Decimal) -> Decimal:
    regular, overtime = split_hours(card)
    gross = regular * hourly_rate + overtime * hourly_rate * OVERTIME_MULTIPLIER
    return gross.quantize(Decimal("0.01"))
