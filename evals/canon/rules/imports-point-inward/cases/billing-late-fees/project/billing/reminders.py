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
            lines.append(f"{invoice.number} {invoice.customer_id} {overdue}d {amount_due(invoice, today)}")
    return lines


if __name__ == "__main__":
    print("\n".join(overdue_lines(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())))
