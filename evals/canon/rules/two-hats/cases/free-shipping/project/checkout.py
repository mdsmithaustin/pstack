"""Order totals shown on the checkout page."""
from shipping import calc_shipping


def order_total(order):
    return order["subtotal_cents"] + calc_shipping(order)
