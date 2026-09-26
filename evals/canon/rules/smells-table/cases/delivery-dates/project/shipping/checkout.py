"""Checkout page copy."""
from shipping.promises import checkout_promise


def arrival_banner(order_date, warehouse_days):
    return f"Arrives by {checkout_promise(order_date, warehouse_days):%a %d %b}"
