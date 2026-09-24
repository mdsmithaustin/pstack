Both classes hold the same customer row for the same invoice, so I kept `Customer` and removed `InvoiceCustomer`.

<file path="invoicing/customer.py">
from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    email: str


def customer_from_row(row: dict) -> Customer:
    return Customer(id=row["customer_id"], name=row["customer_name"], email=row["billing_email"])
</file>

<file path="invoicing/pdf.py">
from invoicing.customer import Customer


def render_header(customer: Customer, invoice_number: str) -> str:
    return f"Invoice {invoice_number}\nBill to: {customer.name} <{customer.email}>\nCustomer no. {customer.id}"
</file>

<file path="invoicing/mailer.py">
from invoicing.customer import Customer


def invoice_message(customer: Customer, invoice_number: str) -> dict:
    return {
        "to": customer.email,
        "subject": f"Your invoice {invoice_number}",
        "body": f"Hello {customer.name}, your invoice {invoice_number} is attached.",
    }
</file>

<file path="invoicing/rows.py">
</file>

<file path="invoicing/send.py">
from invoicing.customer import customer_from_row
from invoicing.mailer import invoice_message
from invoicing.pdf import render_header


def prepare(row: dict, invoice_number: str) -> tuple[str, dict]:
    customer = customer_from_row(row)
    return render_header(customer, invoice_number), invoice_message(customer, invoice_number)
</file>
