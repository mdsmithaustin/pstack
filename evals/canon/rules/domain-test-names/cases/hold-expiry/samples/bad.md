<file path="tests/test_resv.py">
import unittest
from datetime import datetime, timedelta

from boxoffice.resv import create_resv, pay_resv, resv_status

NOON = datetime(2026, 5, 1, 12, 0)


class ResvTest(unittest.TestCase):
    def test_create_resv_returns_active_resv(self):
        resv = create_resv(["A1", "A2"], NOON)

        self.assertEqual(resv_status(resv, NOON), "active")

    def test_pay_resv_sets_status_booked(self):
        resv = create_resv(["A1"], NOON)

        pay_resv(resv)

        self.assertEqual(resv_status(resv, NOON), "booked")

    def test_resv_status_expired_after_900s(self):
        resv = create_resv(["A1"], NOON)

        self.assertEqual(resv_status(resv, NOON + timedelta(seconds=900)), "expired")


if __name__ == "__main__":
    unittest.main()
</file>
