import json
import unittest
from datetime import date
from pathlib import Path

from report import build_report

ORDERS = json.loads((Path(__file__).parent.parent / "data" / "sample-orders.json").read_text())


class BuildReportTest(unittest.TestCase):
    def test_september_eu_report_lists_paid_orders_by_date(self):
        report = json.loads(build_report(ORDERS, date(2026, 9, 1), "eu"))

        self.assertEqual(report["revenue"], "55.00")
        self.assertEqual([row["order_id"] for row in report["rows"]], ["A-1005", "A-1003"])


if __name__ == "__main__":
    unittest.main()
