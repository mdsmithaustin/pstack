"""Invoices for the monthly billing run."""

TIER_DISCOUNT_PERCENT = {"gold": 10, "silver": 5, "standard": 0}
VAT_PERCENT = {"DE": 19, "FR": 20, "US": 0}


def invoice_total(customer, lines):
    subtotal = sum(line["qty"] * line["unit_cents"] for line in lines)
    discount = subtotal * TIER_DISCOUNT_PERCENT[customer.tier] // 100
    if customer.loyalty_years >= 5:
        discount += subtotal // 50
    net = subtotal - discount
    if not customer.tax_exempt:
        net += net * VAT_PERCENT[customer.country] // 100
    return max(net - customer.credit_cents, 0)


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
