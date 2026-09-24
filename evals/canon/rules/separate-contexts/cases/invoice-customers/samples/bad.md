These look alike, but the PDF and the mail are separate contexts, so I kept both types and documented why.

<file path="invoicing/mailer.py">
from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceCustomer:
    """The mail context's customer. Kept apart from the PDF's Customer on purpose."""

    id: str
    name: str
    email: str


def invoice_message(customer: InvoiceCustomer, invoice_number: str) -> dict:
    return {
        "to": customer.email,
        "subject": f"Your invoice {invoice_number}",
        "body": f"Hello {customer.name}, your invoice {invoice_number} is attached.",
    }
</file>
