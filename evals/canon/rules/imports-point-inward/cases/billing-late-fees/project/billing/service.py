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
    return {"invoice": invoice.number, "amount_due": str(amount_due(invoice, today))}
