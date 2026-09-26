from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceCustomer:
    id: str
    name: str
    email: str


def invoice_message(customer: InvoiceCustomer, invoice_number: str) -> dict:
    return {
        "to": customer.email,
        "subject": f"Your invoice {invoice_number}",
        "body": f"Hello {customer.name}, your invoice {invoice_number} is attached.",
    }
