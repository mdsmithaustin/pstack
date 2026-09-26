import unittest

from check import RULES, grade

RULE, CASE = "regression-scenario", "zero-price"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"
TEST = "tests.test_pricing:FormatPriceTest.test_free_item_shows_zero_dollars"


class ZeroPriceTests(unittest.TestCase):
    def test_literal_label_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_not_blank_assertion_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            ["tests.test_pricing:FormatPriceTest.test_zero_price_is_not_blank asserts no literal expected label"],
        )

    def test_truthy_assertion_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace('self.assertEqual(format_price(0), "$0.00")', "self.assertTrue(format_price(0))")
        self.assertEqual(grade(RULE, CASE, text=answer), [f"{TEST} asserts no literal expected label"])

    def test_bare_assert_against_literal_passes(self):
        answer = (SAMPLES / "good.md").read_text().replace('self.assertEqual(format_price(0), "$0.00")', 'assert format_price(0) == "$0.00"')
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_missing_fix_fails(self):
        answer = (SAMPLES / "good.md").read_text().split('<file path="tests/test_pricing.py">', 1)[1]
        self.assertEqual(grade(RULE, CASE, text='<file path="tests/test_pricing.py">' + answer), [f"{TEST} fails after the fix"])

    def test_literal_that_already_held_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace('self.assertEqual(format_price(0), "$0.00")', 'self.assertEqual(format_price(5), "$0.05")')
        self.assertEqual(grade(RULE, CASE, text=answer), ["new tests pass on the code before the fix"])
