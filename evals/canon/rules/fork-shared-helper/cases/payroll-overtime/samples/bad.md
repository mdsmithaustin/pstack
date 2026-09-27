<file path="timesheets/hours.py">
from dataclasses import dataclass
from decimal import Decimal

REGULAR_WEEK = Decimal("38")


@dataclass(frozen=True)
class TimeCard:
    employee: str
    week: str
    hours: Decimal


def split_hours(card: TimeCard) -> tuple[Decimal, Decimal]:
    regular = min(card.hours, REGULAR_WEEK)
    return regular, card.hours - regular
</file>
