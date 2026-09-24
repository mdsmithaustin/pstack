import unittest

from check import RULES, grade

RULE, CASE = "route-domain-modeling", "order-line-items"


class OrderLineItemsTests(unittest.TestCase):
    def test_amendment_named_from_the_glossary_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_line_item_cancellation_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "no new function or class carries the glossary's Amendment; new names are ['cancel_line_items']",
                "cancel_line_items uses a term CONTEXT.md lists under Avoid",
            ],
        )

    def test_avoided_file_name_fails_even_with_an_amendment_function(self):
        good = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text(encoding="utf-8")
        renamed = good.replace("orders/amend.py", "orders/partial_cancel.py").replace("from orders.amend", "from orders.partial_cancel")

        self.assertEqual(grade(RULE, CASE, text=renamed), ["orders/partial_cancel.py uses a term CONTEXT.md lists under Avoid"])


if __name__ == "__main__":
    unittest.main()
