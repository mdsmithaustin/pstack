import unittest

from rollup.export import format_row


class FormatRowTest(unittest.TestCase):
    def test_formats_total_and_trims_customer(self):
        row = {"id": "1001", "customer": "  ada lovelace", "qty": "3", "unit_price": "4.50"}
        self.assertEqual(format_row(row), "1001,Ada Lovelace,13.50")


if __name__ == "__main__":
    unittest.main()
