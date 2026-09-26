"""Warehouse hand-off queue."""
from shipping.promises import carrier_deadline


def overdue(orders, today):
    return [order["id"] for order in orders if carrier_deadline(order["placed_on"], order["warehouse_days"]) < today]
