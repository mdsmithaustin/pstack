import unittest

from check import RULES, grade

RULE, CASE = "translate-foreign-model", "paylane-webhooks"
CASE_DIR = RULES / RULE / "cases" / CASE


class PaylaneWebhooksTests(unittest.TestCase):
    def test_one_translator_module_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_widened_domain_status_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "Paylane codes appear in domain module payments/model.py",
                "Paylane codes appear in domain module payments/orders.py",
                "Paylane codes spread across 2 modules: payments/model.py, payments/orders.py",
                "PaymentStatus gains Paylane values: AUTH_OK, CAPTURED, DECLINED, REFUNDED_PARTIAL",
            ],
        )

    def test_constants_that_map_nothing_fail(self):
        answer = (
            '<file path="payments/paylane.py">\n'
            '"""Paylane webhook states."""\n'
            'STATES = ("AUTH_OK", "CAPTURED", "DECLINED", "REFUNDED_PARTIAL")\n'
            "</file>\n"
        )
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["payments/paylane.py handles Paylane's codes but imports nothing from payments.model or payments.orders"],
        )

    def test_lowercase_copy_of_a_foreign_value_still_leaks(self):
        answer = (CASE_DIR / "samples" / "good.md").read_text() + (
            '\n<file path="payments/model.py">\n'
            + (CASE_DIR / "project" / "payments" / "model.py").read_text().replace(
                '    FAILED = "failed"\n', '    FAILED = "failed"\n    CAPTURED_PAYMENT = "captured"\n'
            )
            + "</file>\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["PaymentStatus gains Paylane values: captured"])

    def test_annotated_copy_of_a_foreign_value_still_leaks(self):
        answer = (CASE_DIR / "samples" / "good.md").read_text() + (
            '\n<file path="payments/model.py">\n'
            + (CASE_DIR / "project" / "payments" / "model.py").read_text().replace(
                '    FAILED = "failed"\n', '    FAILED = "failed"\n    CAPTURED_PAYMENT: str = "captured"\n'
            )
            + "</file>\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["PaymentStatus gains Paylane values: captured"])

    def test_model_that_does_not_parse_fails(self):
        answer = (CASE_DIR / "samples" / "good.md").read_text() + '\n<file path="payments/model.py">\nclass PaymentStatus(\n</file>\n'
        self.assertEqual(grade(RULE, CASE, text=answer), ["payments/model.py does not parse: '(' was never closed at line 1"])
