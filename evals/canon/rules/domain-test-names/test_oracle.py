import unittest

from check import RULES, grade

RULE, CASE = "domain-test-names", "hold-expiry"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class HoldExpiryTests(unittest.TestCase):
    def test_glossary_name_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_function_name_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "tests.test_resv:test_resv_status_expired_after_900s does not name the Hold",
                "tests.test_resv:test_resv_status_expired_after_900s uses the code abbreviation resv",
            ],
        )

    def test_mixed_name_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace("test_an_unpaid_hold_expires", "test_hold_resv_expires")
        self.assertEqual(grade(RULE, CASE, text=answer), ["tests.test_resv:test_hold_resv_expires_after_15_minutes uses the code abbreviation resv"])

    def test_answer_without_tests_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Done."), ["no new test in the answer"])
