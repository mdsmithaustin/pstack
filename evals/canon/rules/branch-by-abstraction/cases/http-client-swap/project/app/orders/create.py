"""Order creation."""
from app import httpclient


def place_order(user_id, skus):
    return httpclient.post_json("/orders", {"user": user_id, "skus": skus})["id"]
