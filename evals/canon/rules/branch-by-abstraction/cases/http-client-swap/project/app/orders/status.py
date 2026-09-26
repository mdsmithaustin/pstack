"""Order status."""
from app import httpclient


def order_status(order_id):
    return httpclient.get_json(f"/orders/{order_id}")["status"]
