import unittest

from check import RULES, grade

RULE, CASE = "given-when-then-shape", "projects-dashboard"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"
TEST = "tests.test_board:BoardTest.test_archived_project_leaves_the_dashboard"


class ProjectsDashboardTests(unittest.TestCase):
    def test_one_action_between_setup_and_assertion_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_chained_asserts_and_phase_comments_fail(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "tests.test_board:BoardTest.test_archive_project marks its phases with comments",
                "tests.test_board:BoardTest.test_archive_project acts again after asserting",
            ],
        )

    def test_second_action_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "        board.archive_project(apollo.id)\n",
            "        board.archive_project(apollo.id)\n        board.rename_project(apollo.id, \"Artemis\")\n",
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [f"{TEST} has 2 actions after its setup, not one"])

    def test_assertion_blind_to_archiving_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            'self.assertEqual(board.dashboard(), ["Gemini"])', 'self.assertIn("Gemini", board.dashboard())'
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["new tests still pass when archiving keeps the project on the dashboard"])

    def test_answer_without_tests_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Done."), ["no new test in the answer"])
