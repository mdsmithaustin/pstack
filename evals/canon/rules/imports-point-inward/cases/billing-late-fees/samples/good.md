The late fee is a pricing rule, so it lives in `billing/invoices.py`. The flag is stored data, so the service reads it and passes it in.

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


def amount_due(invoice: Invoice, today: date, flagged: bool = False) -> Decimal:
    owed = invoice.amount - invoice.paid
    if not flagged and days_overdue(invoice, today) > LATE_AFTER_DAYS:
        owed += owed * LATE_FEE_RATE
    return owed.quantize(CENT)
</file>

<file path="billing/service.py">
"""Statement lookups behind the billing API."""
from datetime import date
from decimal import Decimal

from billing import store
from billing.invoices import Invoice, amount_due


def to_invoice(row) -> Invoice:
    return Invoice(
        number=row["number"],
        customer_id=row["customer_id"],
        amount=Decimal(row["amount"]),
        paid=Decimal(row["paid"]),
        due=date.fromisoformat(row["due"]),
    )


def statement(number: str, today: date) -> dict:
    invoice = to_invoice(store.load_invoice(number))
    owed = amount_due(invoice, today, flagged=store.is_flagged(invoice.customer_id))
    return {"invoice": invoice.number, "amount_due": str(owed)}
</file>

<file path="billing/reminders.py">
"""Nightly job that lists overdue invoices for the collections team."""
import sys
from datetime import date

from billing import store
from billing.invoices import amount_due, days_overdue
from billing.service import to_invoice


def overdue_lines(today: date) -> list[str]:
    lines = []
    for row in store.open_invoices():
        invoice = to_invoice(row)
        overdue = days_overdue(invoice, today)
        if overdue:
            owed = amount_due(invoice, today, flagged=store.is_flagged(invoice.customer_id))
            lines.append(f"{invoice.number} {invoice.customer_id} {overdue}d {owed}")
    return lines


if __name__ == "__main__":
    print("\n".join(overdue_lines(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())))
</file>
