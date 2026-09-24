Two smells in `billing/invoices.py`. `invoice_total` reads five `Customer` fields and none of its own, which is Feature Envy, so it moves next to `Customer`. `street`, `city`, and `postal_code` travel together through three signatures, which is Data Clumps, so an `Address` parameter object replaces the triple. `billing.run` prints the same invoices before and after.

<commit message="Move Function: invoice_total next to Customer (Feature Envy)">
<file path="billing/customers.py">
"""Customer records from the accounts export."""
from dataclasses import dataclass

TIER_DISCOUNT_PERCENT = {"gold": 10, "silver": 5, "standard": 0}
VAT_PERCENT = {"DE": 19, "FR": 20, "US": 0}


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    tier: str
    country: str
    tax_exempt: bool
    loyalty_years: int
    credit_cents: int
    street: str
    city: str
    postal_code: str


def load_customers(rows):
    return {row["id"]: Customer(**row) for row in rows}


def invoice_total(customer, lines):
    subtotal = sum(line["qty"] * line["unit_cents"] for line in lines)
    discount = subtotal * TIER_DISCOUNT_PERCENT[customer.tier] // 100
    if customer.loyalty_years >= 5:
        discount += subtotal // 50
    net = subtotal - discount
    if not customer.tax_exempt:
        net += net * VAT_PERCENT[customer.country] // 100
    return max(net - customer.credit_cents, 0)
</file>
<file path="billing/invoices.py">
"""Invoices for the monthly billing run."""
from billing.customers import invoice_total


def format_address(street, city, postal_code):
    return f"{street}\n{postal_code} {city}"


def shipping_zone(street, city, postal_code):
    if not street:
        return "pickup"
    return "local" if city == "Berlin" and postal_code.startswith("10") else "national"


def mailing_label(name, street, city, postal_code):
    return f"{name}\n{format_address(street, city, postal_code)}"


def render_invoice(customer, lines):
    total = invoice_total(customer, lines)
    zone = shipping_zone(customer.street, customer.city, customer.postal_code)
    label = mailing_label(customer.name, customer.street, customer.city, customer.postal_code)
    return f"{label}\nzone: {zone}\ntotal: {total / 100:.2f}"
</file>
<file path="tests/test_invoices.py">
import unittest

from billing.customers import Customer, invoice_total
from billing.invoices import render_invoice

GOLD = Customer("c1", "Anja Weber", "gold", "DE", False, 6, 500, "Torstr. 1", "Berlin", "10119")


class InvoiceTest(unittest.TestCase):
    def test_gold_loyal_customer_gets_both_discounts_then_vat_then_credit(self):
        lines = [{"qty": 3, "unit_cents": 1999}, {"qty": 1, "unit_cents": 4500}]

        self.assertEqual(invoice_total(GOLD, lines), 10494)

    def test_rendered_invoice_carries_label_zone_and_total(self):
        lines = [{"qty": 1, "unit_cents": 10000}]

        self.assertEqual(
            render_invoice(GOLD, lines),
            "Anja Weber\nTorstr. 1\n10119 Berlin\nzone: local\ntotal: 99.72",
        )


if __name__ == "__main__":
    unittest.main()
</file>
</commit>

<commit message="Introduce Parameter Object: Address replaces street, city, postal_code (Data Clumps)">
<file path="billing/customers.py">
"""Customer records from the accounts export."""
from dataclasses import dataclass

TIER_DISCOUNT_PERCENT = {"gold": 10, "silver": 5, "standard": 0}
VAT_PERCENT = {"DE": 19, "FR": 20, "US": 0}


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    postal_code: str


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    tier: str
    country: str
    tax_exempt: bool
    loyalty_years: int
    credit_cents: int
    street: str
    city: str
    postal_code: str

    @property
    def address(self):
        return Address(self.street, self.city, self.postal_code)


def load_customers(rows):
    return {row["id"]: Customer(**row) for row in rows}


def invoice_total(customer, lines):
    subtotal = sum(line["qty"] * line["unit_cents"] for line in lines)
    discount = subtotal * TIER_DISCOUNT_PERCENT[customer.tier] // 100
    if customer.loyalty_years >= 5:
        discount += subtotal // 50
    net = subtotal - discount
    if not customer.tax_exempt:
        net += net * VAT_PERCENT[customer.country] // 100
    return max(net - customer.credit_cents, 0)
</file>
<file path="billing/invoices.py">
"""Invoices for the monthly billing run."""
from billing.customers import invoice_total


def format_address(address):
    return f"{address.street}\n{address.postal_code} {address.city}"


def shipping_zone(address):
    if not address.street:
        return "pickup"
    return "local" if address.city == "Berlin" and address.postal_code.startswith("10") else "national"


def mailing_label(name, address):
    return f"{name}\n{format_address(address)}"


def render_invoice(customer, lines):
    total = invoice_total(customer, lines)
    zone = shipping_zone(customer.address)
    label = mailing_label(customer.name, customer.address)
    return f"{label}\nzone: {zone}\ntotal: {total / 100:.2f}"
</file>
</commit>
