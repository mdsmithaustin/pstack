import unittest

from check import grade

RULE = "review-deletion-reframe"
DENY, PURGE = "discord-actions-deny", "discord-purge-messages"
UNNAMED = ["the review does not name the file or symbol under review"]


class DiscordActionsDenyTests(unittest.TestCase):
    def test_found_review_names_the_config_gates(self):
        self.assertEqual(grade(RULE, DENY, "review-found.md"), [])

    def test_partial_review_names_the_config_gates(self):
        self.assertEqual(grade(RULE, DENY, "review-partial.md"), [])

    def test_missed_review_names_the_parser(self):
        self.assertEqual(grade(RULE, DENY, "review-missed.md"), [])

    def test_review_that_names_no_config_code_fails(self):
        self.assertEqual(grade(RULE, DENY, text="The deny list is a nice idea. LGTM."), UNNAMED)


class DiscordPurgeMessagesTests(unittest.TestCase):
    def test_clean_review_names_the_purge_action(self):
        self.assertEqual(grade(RULE, PURGE, "review-clean.md"), [])

    def test_clean_question_names_the_purge_action(self):
        self.assertEqual(grade(RULE, PURGE, "review-clean-question.md"), [])

    def test_clean_quiet_review_names_the_purge_action(self):
        self.assertEqual(grade(RULE, PURGE, "review-clean-quiet.md"), [])

    def test_false_alarm_names_the_purge_action(self):
        self.assertEqual(grade(RULE, PURGE, "review-false-alarm.md"), [])

    def test_review_that_names_no_purge_code_fails(self):
        self.assertEqual(grade(RULE, PURGE, text="Clearing a channel in one go is handy. LGTM."), UNNAMED)


if __name__ == "__main__":
    unittest.main()
