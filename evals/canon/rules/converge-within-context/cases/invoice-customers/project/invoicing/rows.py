from invoicing.mailer import InvoiceCustomer
from invoicing.pdf import Customer


def customer_from_row(row: dict) -> Customer:
    return Customer(id=row["customer_id"], name=row["customer_name"], email=row["billing_email"])


def invoice_customer_from_row(row: dict) -> InvoiceCustomer:
    return InvoiceCustomer(id=row["customer_id"], name=row["customer_name"], email=row["billing_email"])
