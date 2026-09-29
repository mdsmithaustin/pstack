import unittest

from check import grade

RULE = "review-large-module"
UNNAMED = ["the review does not name the file or symbol under review"]


class AccountsLoginThrottleTests(unittest.TestCase):
    CASE = "accounts-login-throttle"

    def test_found_names_auth_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-found.md"), [])

    def test_cohesion_only_found_names_auth_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-found-cohesion.md"), [])

    def test_partial_names_auth_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-partial.md"), [])

    def test_missed_names_neither(self):
        self.assertEqual(grade(RULE, self.CASE, "review-missed.md"), UNNAMED)

    def test_review_of_another_file_fails(self):
        self.assertEqual(grade(RULE, self.CASE, text="`accounts_auth.py` looks fine. Approve."), UNNAMED)


class SqliteMigrationBackupTests(unittest.TestCase):
    CASE = "sqlite-migration-backup"

    def test_found_names_utils_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-found.md"), [])

    def test_cohesion_only_found_names_utils_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-found-cohesion.md"), [])

    def test_partial_names_utils_py(self):
        self.assertEqual(grade(RULE, self.CASE, "review-partial.md"), [])

    def test_missed_names_neither(self):
        self.assertEqual(grade(RULE, self.CASE, "review-missed.md"), UNNAMED)

    def test_test_utils_is_not_the_module(self):
        self.assertEqual(grade(RULE, self.CASE, text="`tests/db/test_utils.py` is fine. Approve."), UNNAMED)


class AgentJsonlLogTests(unittest.TestCase):
    CASE = "agent-jsonl-log"

    def test_clean_names_the_defaults_table(self):
        self.assertEqual(grade(RULE, self.CASE, "review-clean.md"), [])

    def test_clean_question_names_the_defaults_table(self):
        self.assertEqual(grade(RULE, self.CASE, "review-clean-question.md"), [])

    def test_clean_quiet_names_neither_data_file(self):
        self.assertEqual(grade(RULE, self.CASE, "review-clean-quiet.md"), UNNAMED)

    def test_false_alarm_names_the_defaults_table(self):
        self.assertEqual(grade(RULE, self.CASE, "review-false-alarm.md"), [])

    def test_the_example_config_counts(self):
        self.assertEqual(grade(RULE, self.CASE, text="`cli-config.yaml.example` is fine. Approve."), [])


if __name__ == "__main__":
    unittest.main()
