import unittest
from unittest import mock

from pricing.fetcher import PriceFetcher


class PriceFetcherTests(unittest.TestCase):
    def test_fetch_reads_the_price_json(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"sku": "mug", "amount": 12.5, "currency": "usd"}'
        opener = mock.Mock(return_value=response)

        raw = PriceFetcher("http://prices.test", opener).fetch("mug")

        opener.assert_called_once_with("http://prices.test/prices/mug", timeout=2)
        self.assertEqual(raw["amount"], 12.5)


if __name__ == "__main__":
    unittest.main()
