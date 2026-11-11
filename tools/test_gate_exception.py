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
    def test_captured_v1_111_0_other_branch_status_blocks(self):
        text = '''other_branch_run:
id: "01EXAMPLE"
branch: fix/example
status: completed
head: "8e257437"
head_sha: 8e2574377defd7701ab644ccb11e7a155bd00d75
test_override_reason: "live validation verdict: inconclusive\\nTest exception approved: no operator reason supplied"
verification_plan: none
pr: "https://example.invalid/pull/1"
outcome: passed-with-override
'''
        self.assertEqual(check(text).returncode, 1)

    def test_unparsed_test_exceptions_are_unread(self):
        for record in (
            'test_override_details: "operator approved"\n',
            'TEST_OVERRIDE_REASON: "operator approved"\n',
            'Test exception approved: operator approved\n',
            'TEST EXCEPTION APPROVED: operator approved\n',
            'test override: operator approved\n',
            'test_override_reason:   \nTest exception approved: operator approved\n',
        ):
            for parsed in ("", REASONED, UNAPPROVED):
                with self.subTest(record=record, parsed=parsed):
                    text = RUN.format(record=parsed + record, outcome="passed-with-override")
                    done = check(text)
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertIn("UNREAD", done.stdout)
                    with tempfile.TemporaryDirectory() as directory:
                        saved = Path(directory) / "status.toon"
                        saved.write_text(text, encoding="utf-8")
                        done = subprocess.run([sys.executable, str(SCRIPT), str(saved)], capture_output=True, text=True)
                        self.assertEqual(done.returncode, 2, done.stdout)

    def test_no_reason_placeholder_is_case_insensitive(self):
        record = UNAPPROVED.replace("no operator reason supplied", "NO Operator Reason SUPPLIED")
        self.assertEqual(check(RUN.format(record=record, outcome="passed-with-override")).returncode, 1)

    def test_ci_override_alone_is_not_a_test_exception(self):
        done = check(RUN.format(record='ci_override_reason: "operator approved"\n', outcome="passed-with-override"))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_exception_words_in_another_field_value_are_not_a_record(self):
        for value in (
            "  branch: fix/test-exception\n",
            "current_branch: fix/test-override\n",
            "  summary: The Test exception path was exercised.\n",
            '  findings[1]{id,severity,file,action,description}:\n    review-1,warning,a.py,ask-user,"keys on a `test_override_reason:` line"\n',
        ):
            with self.subTest(value=value):
                done = check(RUN.format(record=value, outcome="passed"))
                self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_help_line_that_repeats_a_parsed_exception_keeps_its_verdict(self):
        repeat = 'help[1]: "Report the approved Test exception, not a clean Test pass: Test exception approved: {reason}"\n'
        for record, reason, code in ((REASONED, "The operator approved the pending live scenario.", 3), (UNAPPROVED, "no operator reason supplied", 1)):
            with self.subTest(code=code):
                done = check(RUN.format(record=record, outcome="checks-passed") + repeat.format(reason=reason))
                self.assertEqual(done.returncode, code, done.stdout)

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

    def test_a_status_missing_a_run_field_is_never_a_pass(self):
        for text in (
            "status: completed\n",
            "head_sha: 8e2574377defd7701ab644ccb11e7a155bd00d75\n",
            'id: "01EXAMPLE"\nstatus: completed\n',
            "status: completed\nhead_sha: 8e2574377defd7701ab644ccb11e7a155bd00d75\n",
        ):
            with self.subTest(text=text):
                done = check(text)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("names no run", done.stdout)

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
