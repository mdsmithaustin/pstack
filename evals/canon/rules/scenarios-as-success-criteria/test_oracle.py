import unittest

from check import RULES, grade

RULE, CASE = "scenarios-as-success-criteria", "refund-window"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class RefundWindowTests(unittest.TestCase):
    def test_handler_examples_first_pass(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_helper_first_with_one_handler_example_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "the first new test, tests.test_refunds:WindowTest.test_day_19_is_within_window, does not go through OrdersApi.handle",
                "no handler test asserts the window closed example's literal 422 and 'refund window closed'",
                "no handler test asserts the not delivered yet example's literal 409 and 'order not delivered'",
            ],
        )

    def test_status_constant_name_counts_as_literal(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "self.assertEqual(response.status, 409)", "self.assertEqual(response.status, HTTPStatus.CONFLICT)"
        ).replace("import unittest\n", "import unittest\nfrom http import HTTPStatus\n", 1)
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_example_that_fails_on_the_answer_code_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace('{"error": "order not delivered"})\n        if self', '{"error": "not delivered"})\n        if self')
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["tests.test_refunds:RefundWindowTest.test_refund_before_delivery_is_refused fails against the answer's code"],
        )

    def test_answer_without_tests_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Done."), ["no new test in the answer"])
