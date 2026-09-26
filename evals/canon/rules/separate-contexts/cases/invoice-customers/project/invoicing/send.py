from invoicing.mailer import invoice_message
from invoicing.pdf import render_header
from invoicing.rows import customer_from_row, invoice_customer_from_row


def prepare(row: dict, invoice_number: str) -> tuple[str, dict]:
    header = render_header(customer_from_row(row), invoice_number)
    message = invoice_message(invoice_customer_from_row(row), invoice_number)
    return header, message
