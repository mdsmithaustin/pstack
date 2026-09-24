import unittest

from check import RULES, grade

RULE = "separate-contexts"
ACCOUNTS = RULES / RULE / "cases" / "account-types" / "samples"


class AccountTypesTests(unittest.TestCase):
    def test_separate_types_with_shared_id_pass(self):
        self.assertEqual(grade(RULE, "account-types", "good.md"), [])

    def test_merged_optional_fields_fail(self):
        self.assertEqual(
            grade(RULE, "account-types", "bad.md"),
            [
                "accounts.py:Account mixes billing fields with sign-in fields",
                "no type keeps the billing account's fields",
                "no type keeps the sign-in account's fields",
            ],
        )

    def test_unchanged_project_passes(self):
        self.assertEqual(grade(RULE, "account-types", text="These are different concepts; I left them apart."), [])


class InvoiceCustomersTests(unittest.TestCase):
    def test_one_merged_customer_passes(self):
        self.assertEqual(grade(RULE, "invoice-customers", "good.md"), [])

    def test_kept_duplicate_fails(self):
        self.assertEqual(
            grade(RULE, "invoice-customers", "bad.md"),
            ["2 types hold a customer's id, name, and email: invoicing/mailer.py:InvoiceCustomer, invoicing/pdf.py:Customer"],
        )
