import unittest

from billing.customers import Customer
from billing.invoices import invoice_total, render_invoice

GOLD = Customer("c1", "Anja Weber", "gold", "DE", False, 6, 500, "Torstr. 1", "Berlin", "10119")


class InvoiceTest(unittest.TestCase):
    def test_gold_loyal_customer_gets_both_discounts_then_vat_then_credit(self):
        lines = [{"qty": 3, "unit_cents": 1999}, {"qty": 1, "unit_cents": 4500}]

        self.assertEqual(invoice_total(GOLD, lines), 10494)

    def test_rendered_invoice_carries_label_zone_and_total(self):
        lines = [{"qty": 1, "unit_cents": 10000}]

        self.assertEqual(
            render_invoice(GOLD, lines),
            "Anja Weber\nTorstr. 1\n10119 Berlin\nzone: local\ntotal: 99.72",
        )


if __name__ == "__main__":
    unittest.main()
