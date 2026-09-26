"""What a customer owes on an invoice."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Invoice:
    number: str
    customer_id: str
    amount: Decimal
    paid: Decimal
    due: date


def days_overdue(invoice: Invoice, today: date) -> int:
    return max((today - invoice.due).days, 0)


def amount_due(invoice: Invoice, today: date) -> Decimal:
    return (invoice.amount - invoice.paid).quantize(CENT)
