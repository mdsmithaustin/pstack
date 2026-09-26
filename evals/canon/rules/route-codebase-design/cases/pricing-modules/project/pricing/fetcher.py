"""Reads list prices from the pricing service the catalog team runs."""
import json
import urllib.request

PRICING_URL = "http://pricing.internal:8080"


class PriceFetcher:
    def __init__(self, base_url=PRICING_URL, opener=urllib.request.urlopen):
        self.base_url = base_url
        self.opener = opener

    def fetch(self, sku):
        with self.opener(f"{self.base_url}/prices/{sku}", timeout=2) as response:
            return json.loads(response.read())
