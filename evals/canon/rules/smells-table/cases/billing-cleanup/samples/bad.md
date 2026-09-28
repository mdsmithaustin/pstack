`invoice_total` does three jobs, so I pulled each into a helper in a new `billing/helpers.py` and gave the address code a shared formatter. Output is unchanged.

<commit message="Clean up billing invoices">
<file path="billing/helpers.py">
"""Helpers for invoice math and addresses."""

TIER_DISCOUNT_PERCENT = {"gold": 10, "silver": 5, "standard": 0}
VAT_PERCENT = {"DE": 19, "FR": 20, "US": 0}


def subtotal_cents(lines):
    return sum(line["qty"] * line["unit_cents"] for line in lines)


def discount_cents(customer, subtotal):
    discount = subtotal * TIER_DISCOUNT_PERCENT[customer.tier] // 100
    if customer.loyalty_years >= 5:
        discount += subtotal // 50
    return discount


def with_vat(customer, net):
    if customer.tax_exempt:
        return net
    return net + net * VAT_PERCENT[customer.country] // 100
</file>
<file path="billing/invoices.py">
"""Invoices for the monthly billing run."""
from billing.helpers import discount_cents, subtotal_cents, with_vat


def invoice_total(customer, lines):
    subtotal = subtotal_cents(lines)
    net = subtotal - discount_cents(customer, subtotal)
    return max(with_vat(customer, net) - customer.credit_cents, 0)


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
</commit>
