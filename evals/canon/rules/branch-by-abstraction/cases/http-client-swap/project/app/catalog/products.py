"""Product lookups."""
from app import httpclient


def fetch_product(sku):
    return httpclient.get_json(f"/products/{sku}")


def search_products(term):
    return httpclient.get_json(f"/products?q={term}")["items"]
