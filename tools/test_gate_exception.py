import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/poteto-mode/scripts/gate-exception.py"
REFERENCE = ROOT / "skills/poteto-mode/references/gated-publish.md"
RUN = """current_branch: fix/example
run:
  id: "01EXAMPLE"
  status: completed
  head_sha: 8e2574377defd7701ab644ccb11e7a155bd00d75
{record}  pr: "https://example.invalid/pull/1"
outcome: {outcome}
"""
UNAPPROVED = '  test_override_reason: "live validation verdict: inconclusive\\nTest exception approved: no operator reason supplied"\n'
REASONED = '  test_override_reason: "live validation verdict: inconclusive\\nTest exception approved: The operator approved the pending live scenario."\n'


def check(text):
    return subprocess.run([sys.executable, str(SCRIPT)], input=text, capture_output=True, text=True)


class GateException(unittest.TestCase):
    def test_a_run_with_no_exception_passes(self):
        done = check(RUN.format(record="", outcome="passed"))
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "PASS: no Test exception is recorded."))

    def test_an_exception_with_no_operator_reason_blocks(self):
        done = check(RUN.format(record=UNAPPROVED, outcome="passed-with-override"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stdout)
        self.assertIn("no operator reason supplied", done.stdout)

    def test_an_exception_with_a_reason_needs_a_match_and_never_passes(self):
        done = check(RUN.format(record=REASONED, outcome="passed-with-override"))
        self.assertEqual(done.returncode, 3)
        self.assertIn("The operator approved the pending live scenario.", done.stdout)
        self.assertIn("operator's own approval", done.stdout)

    def test_the_worst_record_decides_when_the_status_holds_several_runs(self):
        text = RUN.format(record=REASONED, outcome="passed-with-override") + RUN.format(record=UNAPPROVED, outcome="passed-with-override")
        done = check(text)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("MATCH", done.stdout)

    def test_unreadable_status_is_never_a_pass(self):
        for text in ("", "  \n", "error: repo not initialized\n", "no-mistakes: command not found\n"):
            with self.subTest(text=text):
                done = check(text)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("Nothing was checked", done.stdout)

    def test_an_error_beside_run_fields_is_still_unread(self):
        self.assertEqual(check("error: daemon unavailable\n" + RUN.format(record="", outcome="passed")).returncode, 2)

    def test_it_reads_a_file_and_reports_a_missing_one_as_unread(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "status.toon"
            saved.write_text(RUN.format(record=UNAPPROVED, outcome="passed-with-override"), encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(saved)], capture_output=True, text=True).returncode, 1)
            missing = subprocess.run([sys.executable, str(SCRIPT), str(saved) + ".absent"], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 2)

    def test_gated_publish_runs_the_check_and_names_every_exit(self):
        text = REFERENCE.read_text(encoding="utf-8")
        self.assertIn('poteto-mode/scripts/gate-exception.py"', text)
        for code in ("Exit 0", "Exit 1", "Exit 2", "Exit 3"):
            self.assertIn(code, text)


if __name__ == "__main__":
    unittest.main()
