"""Price lookups."""
from app import httpclient


def current_price(sku):
    return httpclient.get_json(f"/prices/{sku}")["cents"]
