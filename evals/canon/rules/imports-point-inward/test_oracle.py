import unittest

from check import RULES, grade

RULE, CASE = "imports-point-inward", "billing-late-fees"
GOOD = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text()


class BillingLateFeesTests(unittest.TestCase):
    def test_flag_passed_in_as_data_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_policy_importing_the_store_fails(self):
        self.assertEqual(grade(RULE, CASE, "bad.md"), ["billing.invoices imports billing.store"])

    def test_type_only_import_counts(self):
        answer = GOOD.replace(
            "from decimal import Decimal\n\nCENT",
            "from decimal import Decimal\nfrom typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from sqlite3 import Row\n\nCENT",
            1,
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["billing.invoices imports sqlite3"])

    def test_leak_through_a_new_policy_module_fails(self):
        answer = GOOD.replace('CENT = Decimal("0.01")', 'from billing import late_fees\n\nCENT = Decimal("0.01")', 1)
        answer += '\n<file path="billing/late_fees.py">\nfrom billing import store\n</file>\n'
        self.assertEqual(grade(RULE, CASE, text=answer), ["billing.late_fees imports billing.store"])

    def test_unchanged_project_fails(self):
        self.assertEqual(grade(RULE, CASE, text="The project already does this."), ["answer changes no file"])


if __name__ == "__main__":
    unittest.main()
