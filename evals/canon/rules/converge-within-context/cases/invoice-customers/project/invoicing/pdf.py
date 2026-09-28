from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    email: str


def render_header(customer: Customer, invoice_number: str) -> str:
    return f"Invoice {invoice_number}\nBill to: {customer.name} <{customer.email}>\nCustomer no. {customer.id}"
