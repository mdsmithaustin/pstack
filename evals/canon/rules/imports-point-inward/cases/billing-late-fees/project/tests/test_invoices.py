import unittest
from datetime import date
from decimal import Decimal

from billing.invoices import Invoice, amount_due, days_overdue


def invoice(amount="100.00", paid="0.00", due=date(2026, 9, 1)):
    return Invoice("INV-9", "c9", Decimal(amount), Decimal(paid), due)


class AmountDueTests(unittest.TestCase):
    def test_owes_the_unpaid_part(self):
        self.assertEqual(amount_due(invoice(paid="40.00"), date(2026, 9, 2)), Decimal("60.00"))

    def test_counts_days_after_the_due_date(self):
        self.assertEqual(days_overdue(invoice(), date(2026, 9, 11)), 10)

    def test_is_not_overdue_before_the_due_date(self):
        self.assertEqual(days_overdue(invoice(), date(2026, 8, 20)), 0)


if __name__ == "__main__":
    unittest.main()
