import unittest

from check import RULES, grade

RULE, CASE = "example-mapping", "withdrawal-story"
INVENTED = "a Then asserts an outcome for a withdrawal that lands exactly on -£100"
GOOD = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text()


class WithdrawalStoryTests(unittest.TestCase):
    def test_examples_with_an_open_at_limit_question_pass(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_invented_at_limit_outcome_fails(self):
        self.assertEqual(grade(RULE, CASE, "bad.md"), [INVENTED])

    def test_minimum_example_that_pays_out_fails(self):
        answer = GOOD.replace(
            'Then the withdrawal is refused with "The minimum withdrawal is £10"\nAnd my balance is still £200',
            "Then I receive £5\nAnd my balance is £195",
        )
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["a Then for the minimum rule contradicts the story: I receive £5; my balance is £195"],
        )

    def test_paid_example_with_the_wrong_balance_fails(self):
        answer = GOOD.replace("Then I receive £40\nAnd my balance is £10", "Then I receive £40\nAnd my balance is £50")
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["a Then for the paid rule contradicts the story: I receive £40; my balance is £50"],
        )

    def test_paid_example_with_the_wrong_amount_received_fails(self):
        answer = GOOD.replace("Then I receive £40\nAnd my balance is £10", "Then I receive £999\nAnd my balance is £10")
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["a Then for the paid rule contradicts the story: I receive £999; my balance is £10"],
        )

    def test_prose_criteria_fail(self):
        answer = (
            "- Withdrawals under £10 are refused.\n"
            "- Withdrawals that keep the balance above -£100 are paid out.\n"
            "- Withdrawals that take the balance below -£100 are refused.\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["no Given, When, Then examples"])

    def test_table_examples_with_a_question_line_pass(self):
        answer = (
            "| Rule | Given | When | Then |\n"
            "|---|---|---|---|\n"
            "| Minimum | balance of £200 | I withdraw £5 | refused with \"The minimum withdrawal is £10\" |\n"
            "| Paid out | balance of £0 | I withdraw £80 | I receive £80 and my balance is -£80 |\n"
            "| Refused | balance of £0 | I withdraw £120 | refused with \"Insufficient funds\" |\n"
            "\n"
            "Open question: is a withdrawal that leaves the balance at exactly -£100 paid out or refused?\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_inline_sentences_with_an_invented_limit_outcome_fail(self):
        answer = (
            "1. Given my balance is £200, when I withdraw £5, then it is refused.\n"
            "2. Given I am £30 overdrawn, when I withdraw £20, then I receive £20.\n"
            "3. Given I am overdrawn by £30, when I withdraw £90, then it is refused.\n"
            "4. Given my balance is £0 and my overdraft limit is £100, when I withdraw £100, then it is refused.\n"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [INVENTED])

    def test_missing_rule_and_silent_limit_fail(self):
        answer = (
            "Given my balance is £50\nWhen I withdraw £40\nThen I receive £40\n\n"
            "Given my balance is £50\nWhen I withdraw £200\nThen the withdrawal is refused\n"
        )
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            [
                "no example with literal amounts and a Then for the minimum rule",
                "the withdrawal that lands exactly on -£100 is not raised as an open question",
            ],
        )


if __name__ == "__main__":
    unittest.main()
