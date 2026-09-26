import unittest

from check import grade

RULE, CASE = "explicit-as-scenario", "loyalty-points"
MISSING = ["LP-1's part-of-a-pound rule has no Given, When, Then example with a literal Then"]


class LoyaltyPointsTests(unittest.TestCase):
    def test_scenario_resolution_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_prose_resolution_fails(self):
        self.assertEqual(grade(RULE, CASE, "bad.md"), MISSING)

    def test_table_row_on_top_of_existing_points_passes(self):
        answer = (
            "| Given | When | Then |\n"
            "|---|---|---|\n"
            "| a customer with 20 points | they place a £12.50 order | they have 32 points |\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_rounding_up_is_not_the_stated_answer(self):
        answer = "Given a customer with 0 points\nWhen they place an order totalling £9.99\nThen they have 10 points\n"
        self.assertEqual(grade(RULE, CASE, text=answer), MISSING)

    def test_open_then_is_not_literal(self):
        answer = "Given a customer with 0 points\nWhen they place an order totalling £9.99\nThen they have 9 points?\n"
        self.assertEqual(grade(RULE, CASE, text=answer), MISSING)


if __name__ == "__main__":
    unittest.main()
