import unittest
from decimal import Decimal

from invoicing.totals import credit_note_total, invoice_total


class TotalsTests(unittest.TestCase):
    def test_invoice_adds_vat_to_the_line_total(self):
        self.assertEqual(invoice_total([(Decimal("19.99"), 3)], Decimal("0.20")), Decimal("71.96"))

    def test_credit_note_reverses_the_same_lines(self):
        self.assertEqual(credit_note_total([(Decimal("19.99"), 3)], Decimal("0.20")), Decimal("-71.96"))


if __name__ == "__main__":
    unittest.main()
