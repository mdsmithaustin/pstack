import unittest

from check import RULES, grade

RULE = "same-decision-only"
SEPARATE, MERGED = "payroll-invoice-rounding", "invoice-credit-rounding"


def sample(case, name):
    return (RULES / RULE / "cases" / case / "samples" / name).read_text()


class PayrollInvoiceRoundingTests(unittest.TestCase):
    def test_separate_helpers_pass(self):
        self.assertEqual(grade(RULE, SEPARATE, "good.md"), [])

    def test_shared_money_module_fails(self):
        self.assertEqual(grade(RULE, SEPARATE, "bad.md"), ["net_pay and invoice_total share money.round_money"])

    def test_leaving_the_code_alone_passes(self):
        self.assertEqual(grade(RULE, SEPARATE, text="These are two decisions, so nothing changes."), [])

    def test_importing_the_other_modules_helper_fails(self):
        invoicing = sample(SEPARATE, "bad.md").split('<file path="invoicing/totals.py">')[1]
        answer = '<file path="invoicing/totals.py">' + invoicing.replace("from money import round_money", "from payroll.pay import round_money")
        self.assertEqual(grade(RULE, SEPARATE, text=answer), ["net_pay and invoice_total share payroll.pay.round_money"])

    def test_changed_rounding_fails(self):
        answer = sample(SEPARATE, "good.md").replace("rounding=ROUND_HALF_UP)\n\n\ndef net_pay", "rounding=ROUND_HALF_EVEN)\n\n\ndef net_pay").replace(
            "from decimal import ROUND_HALF_UP, Decimal\n\n\ndef round_pay", "from decimal import ROUND_HALF_EVEN, Decimal\n\n\ndef round_pay"
        )
        self.assertEqual(
            grade(RULE, SEPARATE, text=answer),
            ["net_pay results changed from ['2250.00', '750.07', '1759.26', '749.99'] to ['2250.00', '750.08', '1759.26', '749.99']"],
        )


class InvoiceCreditRoundingTests(unittest.TestCase):
    def test_one_rounding_helper_passes(self):
        self.assertEqual(grade(RULE, MERGED, "good.md"), [])

    def test_leaving_both_copies_fails(self):
        self.assertEqual(grade(RULE, MERGED, "bad.md"), ["invoice_total and credit_note_total still repeat the rounding"])


if __name__ == "__main__":
    unittest.main()
