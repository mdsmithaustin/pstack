import unittest
from decimal import Decimal

from invoicing.totals import invoice_total
from payroll.pay import net_pay


class NetPayTests(unittest.TestCase):
    def test_takes_tax_and_pension_off_gross(self):
        self.assertEqual(net_pay(Decimal("3000.00"), Decimal("0.20"), Decimal("0.05")), Decimal("2250.00"))


class InvoiceTotalTests(unittest.TestCase):
    def test_adds_vat_to_the_line_total(self):
        self.assertEqual(invoice_total([(Decimal("19.99"), 3)], Decimal("0.20")), Decimal("71.96"))


if __name__ == "__main__":
    unittest.main()
