The fee applies wherever `amount_due` runs, so the statement and the reminders both pick it up without changes.

<file path="billing/invoices.py">
"""What a customer owes on an invoice."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

CENT = Decimal("0.01")
LATE_AFTER_DAYS = 30
LATE_FEE_RATE = Decimal("0.02")


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
    from billing.store import is_flagged

    owed = invoice.amount - invoice.paid
    if days_overdue(invoice, today) > LATE_AFTER_DAYS and not is_flagged(invoice.customer_id):
        owed += owed * LATE_FEE_RATE
    return owed.quantize(CENT)
</file>
