import shlex
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/pstack-harness/scripts/subagents.py"


def clauses(*args):
    done = subprocess.run([sys.executable, str(SCRIPT), "clauses", *args], capture_output=True, text=True)
    return done.returncode, done.stdout


class BriefClauses(unittest.TestCase):
    def test_committing_brief_carries_every_required_clause(self):
        code, text = clauses("--source", "/work/task.md", "--start-commit", "abc123", "--branch", "feat/x")
        self.assertEqual(code, 0)
        self.assertIn("Read the original task in full before any work: /work/task.md.", text)
        self.assertIn("each marked quoted, current behavior, or inferred.", text)
        self.assertIn("Build what you can trace to the source or to the file a mark names.", text)
        self.assertIn("Report what you cannot trace with the work. Stop without building only when it decides what to build.", text)
        self.assertIn("This run is attended.", text)
        self.assertIn("Commit on branch feat/x, off trunk", text)
        self.assertIn("credential files such as `.env`", text)
        self.assertIn('preserve.py" --since abc123', text)
        self.assertIn("before every commit or amend", text)
        self.assertIn("nested delegates, replacement owners, and fix rounds", text)

    def test_read_rule_comes_before_the_first_read_it_governs(self):
        for arguments in (("--source", "t.md"), ("--source", "t.md", "--no-commits")):
            with self.subTest(arguments=arguments):
                text = clauses(*arguments)[1]
                self.assertTrue(text.startswith("- A cut-off read is no read. "), text)
                self.assertLess(text.index("read-plan.py"), text.index("Read the original task in full"))
                self.assertIn(shlex.quote(str(SCRIPT.with_name("read-plan.py"))), text)

    def test_cleanup_cadence_follows_the_run(self):
        self.assertIn("before each push, over every commit not yet pushed", clauses("--source", "t.md", "--cleanup", "push")[1])

    def test_unattended_state_reaches_the_brief(self):
        self.assertIn("This run is unattended. Do not wait for a human reply.", clauses("--source", "t.md", "--unattended")[1])

    def test_no_commits_brief_drops_commit_clauses(self):
        text = clauses("--source", "t.md", "--no-commits")[1]
        self.assertIn("Do not commit. Return the uncommitted diff", text)
        self.assertNotIn("preserve.py", text)

    def test_project_without_a_repository_names_no_branch(self):
        self.assertIn("no repository trunk yet", clauses("--source", "t.md")[1])

    def test_a_start_commit_with_a_space_stays_one_argument(self):
        text = clauses("--source", "t.md", "--start-commit", "no commits")[1]
        self.assertIn("preserve.py\" --since 'no commits'`", text)

    def test_a_bug_fix_delegate_lands_the_reproducer_first(self):
        text = clauses("--source", "t.md", "--failing-test-first")[1]
        self.assertIn("Land the failing reproducer in its own commit before the fix", text)
        self.assertNotIn("Commit the tests with the code that passes them.", text)
        self.assertIn("Commit the tests with the code that passes them.", clauses("--source", "t.md")[1])

    def test_source_is_required(self):
        self.assertEqual(clauses()[0], 2)


if __name__ == "__main__":
    unittest.main()
