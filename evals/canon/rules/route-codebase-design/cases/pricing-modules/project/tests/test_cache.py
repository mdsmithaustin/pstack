import unittest
from unittest import mock

from pricing.cache import PriceCache


class PriceCacheTests(unittest.TestCase):
    def test_put_then_get_returns_the_price(self):
        price = mock.Mock(sku="mug")
        cache = PriceCache()

        cache.put(price)

        self.assertIs(cache.get("mug"), price)

    def test_unknown_sku_misses(self):
        self.assertIsNone(PriceCache().get("tee"))


if __name__ == "__main__":
    unittest.main()
