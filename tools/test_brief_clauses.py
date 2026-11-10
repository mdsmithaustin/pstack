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
        self.assertIn("This run is attended.", text)
        self.assertIn("Commit on branch feat/x, off trunk", text)
        self.assertIn("credential files such as `.env`", text)
        self.assertIn('preserve.py" --since abc123', text)
        self.assertIn("before every commit or amend", text)
        self.assertIn("nested delegates, replacement owners, and fix rounds", text)

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

    def test_source_is_required(self):
        self.assertEqual(clauses()[0], 2)


if __name__ == "__main__":
    unittest.main()
