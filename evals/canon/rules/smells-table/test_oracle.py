import unittest

from check import RULES, grade

RULE, BILLING, DATES = "smells-table", "billing-cleanup", "delivery-dates"
PROJECT = RULES / RULE / "cases" / BILLING / "project"


class BillingCleanupTests(unittest.TestCase):
    def test_moved_function_and_parameter_object_pass(self):
        self.assertEqual(grade(RULE, BILLING, "good.md"), [])

    def test_helper_module_fails(self):
        self.assertEqual(
            grade(RULE, BILLING, "bad.md"),
            [
                "adds helper module billing/helpers.py",
                "billing/helpers.py:subtotal_cents is a new function with one caller",
                "billing/helpers.py:discount_cents is a new function with one caller",
                "billing/helpers.py:with_vat is a new function with one caller",
                "billing/invoices.py:format_address still takes street, city, and postal_code",
                "billing/invoices.py:shipping_zone still takes street, city, and postal_code",
                "billing/invoices.py:mailing_label still takes street, city, and postal_code",
            ],
        )

    def test_unchanged_invoices_keep_the_envious_function(self):
        body = (PROJECT / "billing" / "invoices.py").read_text()
        answer = f'<commit message="Move Function and Introduce Parameter Object">\n<file path="billing/invoices.py">\n{body}</file>\n</commit>\n'
        self.assertEqual(
            grade(RULE, BILLING, text=answer),
            [
                "billing/invoices.py:invoice_total reads 5 Customer fields outside the Customer module",
                "billing/invoices.py:format_address still takes street, city, and postal_code",
                "billing/invoices.py:shipping_zone still takes street, city, and postal_code",
                "billing/invoices.py:mailing_label still takes street, city, and postal_code",
            ],
        )


class DeliveryDatesTests(unittest.TestCase):
    def test_separate_copies_pass(self):
        self.assertEqual(grade(RULE, DATES, "good.md"), [])

    def test_shared_helper_fails(self):
        self.assertEqual(grade(RULE, DATES, "bad.md"), ["checkout_promise and carrier_deadline share add_business_days"])

    def test_alias_is_not_its_own_function(self):
        answer = (RULES / RULE / "cases" / DATES / "samples" / "good.md").read_text()
        start = answer.index("def carrier_deadline")
        aliased = answer[:start] + "carrier_deadline = checkout_promise\n</file>\n</commit>\n"
        self.assertEqual(grade(RULE, DATES, text=aliased), ["carrier_deadline is not its own function in shipping/promises.py"])


if __name__ == "__main__":
    unittest.main()
