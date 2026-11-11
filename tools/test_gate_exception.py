"""Tests for the Test exception check.

The files under tools/testdata/gate-exception are `no-mistakes axi status --run`, `axi status --branch`, and
`axi rounds --step test --json` output from v1.111.0, saved as printed. Two edits only: the account name in
home-directory paths became `<user>`, and the session scratch directory became `<scratchpad>`. Both sit in
`verification_plan` lines, which the check does not read.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/poteto-mode/scripts/gate-exception.py"
REFERENCE = ROOT / "skills/poteto-mode/references/gated-publish.md"
CAPTURES = ROOT / "tools/testdata/gate-exception"
RUN = """current_branch: fix/example
run:
  id: "{id}"
  status: {status}
  head_sha: 8e2574377defd7701ab644ccb11e7a155bd00d75
{record}  pr: "https://example.invalid/pull/1"
outcome: {outcome}
"""
UNAPPROVED = '  test_override_reason: "live validation verdict: inconclusive\\nTest exception approved: no operator reason supplied"\n'
REASONED = '  test_override_reason: "live validation verdict: inconclusive\\nTest exception approved: The operator approved the pending live scenario."\n'
ROUND = {"round": 1, "trigger": "initial", "summary": "Six scenarios passed.", "findings": None, "selected_finding_ids": None}
FINDING = {"action": "ask-user", "category": "test-verdict", "description": "two scenarios untested", "id": "test-1", "severity": "warning"}


def run(record="", outcome="passed", status="completed", id="01EXAMPLE"):
    return RUN.format(record=record, outcome=outcome, status=status, id=id)


def check(text, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=text, capture_output=True, text=True)


def check_capture(status, rounds=None):
    args = [str(CAPTURES / f"status-{status}.txt")] + (["--rounds", str(CAPTURES / f"rounds-{rounds}.json")] if rounds else [])
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def check_history(history, text=None):
    with tempfile.TemporaryDirectory() as directory:
        saved = Path(directory) / "rounds.json"
        saved.write_text(history if isinstance(history, str) else json.dumps(history), encoding="utf-8")
        return check(text or run(), "--rounds", str(saved))


def history(*rounds, **fields):
    return {"schema_version": 1, "run_id": "01EXAMPLE", "step": "test", "rounds": list(rounds)} | fields


class GateException(unittest.TestCase):
    def test_real_status_captures(self):
        for status, code, said in (
            ("exception-with-reason", 3, "with this reason: Operator, 2026-11-11: I approve without live validation."),
            ("incident-no-reason", 1, "BLOCKED: run 01M6S1JPSPRNCZT52A28F74V1V (completed)"),
            ("clean-completed", 0, "Not read: the Test round history"),
            ("cancelled-with-record", 3, "run 01M76080AZEBA1X2QG6VNCFMV6 (cancelled) records a Test exception with this reason: Operator approved"),
            ("cancelled-no-record", 2, "NO VERDICT: run 01M765RYME5ER1DPQ5P46SFG6R (cancelled) ended cancelled"),
            ("failed-no-record", 2, "NO VERDICT: run 01M765HEYR39DY25N2X6VQZJKF (failed) ended failed"),
            ("round-1-record", 3, "run 01M75NQEKPN4N4VPNHXXNZR5NQ (running) records a Test exception"),
            ("round-2-record-gone", 0, "an exception in an earlier Test round of this run is not ruled out"),
            ("branch-form", 2, "Pass `no-mistakes axi status --run <run-id>` output"),
            ("gate-error", 2, "UNREAD: the gate returned an error"),
        ):
            with self.subTest(status=status):
                done = check_capture(status)
                self.assertEqual(done.returncode, code, done.stdout)
                self.assertIn(said, done.stdout)

    def test_real_round_history_captures(self):
        for status, rounds, code, said in (
            ("round-2-record-gone", "record-gone", 3, "Test round 1 left finding test-1 (ask-user) unfixed: live validation verdict: inconclusive"),
            ("round-1-record", "record-gone", 3, "records a Test exception with this reason"),
            ("exception-with-reason", "exception-with-reason", 3, "I approve without live validation."),
            ("incident-no-reason", "incident-no-reason", 1, "no operator reason supplied"),
            ("clean-completed", "clean-completed", 0, "none of its 1 Test round(s) left a finding unfixed"),
            ("cancelled-question-accepted", "cancelled-question-accepted", 3, "Test round 2 left finding test-1 (ask-user) unfixed"),
            ("clean-completed", "record-gone", 2, "UNREAD: the round history"),
        ):
            with self.subTest(status=status, rounds=rounds):
                done = check_capture(status, rounds)
                self.assertEqual(done.returncode, code, done.stdout)
                self.assertIn(said, done.stdout)

    def test_a_dropped_record_is_reported_with_every_round_summary(self):
        done = check_capture("round-2-record-gone", "record-gone")
        self.assertIn("The two previously accepted live-agent coverage gaps remain untested.", done.stdout)
        self.assertIn("The round history keeps no reason.", done.stdout)

    def test_a_real_fix_round_that_cleared_its_findings_leaves_nothing_unfixed(self):
        done = check(run(id="01M75PTKRGZT79PA5BB1FJWYJ2"), "--rounds", str(CAPTURES / "rounds-auto-fixed.json"))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("none of its 2 Test round(s)", done.stdout)

    def test_no_exit_0_message_claims_a_clean_test(self):
        for done in (check(run()), check_history(history(ROUND))):
            self.assertEqual(done.returncode, 0, done.stdout)
            self.assertIn("Not proven: that Test drove every scenario.", done.stdout)
            self.assertNotIn("PASS", done.stdout)

    def test_round_findings_decide_only_when_unfixed(self):
        for finding, selected, code in (
            (FINDING, [], 3),
            (FINDING, None, 3),
            (FINDING, ["test-1"], 0),
            (FINDING | {"action": "auto-fix"}, [], 3),
            (FINDING | {"action": "no-op"}, [], 0),
        ):
            with self.subTest(action=finding["action"], selected=selected):
                done = check_history(history(ROUND | {"findings": [finding], "selected_finding_ids": selected}))
                self.assertEqual(done.returncode, code, done.stdout)

    def test_an_unfixed_round_finding_on_an_ended_run_is_still_reported(self):
        done = check_history(history(ROUND | {"findings": [FINDING]}), run(status="cancelled", outcome="cancelled") + 'error: "cancelled: superseded by new push"\n')
        self.assertEqual(done.returncode, 3, done.stdout)

    def test_round_history_that_is_not_this_runs_test_rounds_is_unread(self):
        for document in (
            history(ROUND, schema_version=2),
            history(ROUND, step="review"),
            history(ROUND, run_id="01OTHER"),
            history({"round": 1}),
            {"rounds": []},
            [],
            "not json",
        ):
            for record in ("", UNAPPROVED):
                with self.subTest(document=document, record=record):
                    done = check_history(document, run(record))
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertIn("Nothing was checked", done.stdout)
        self.assertEqual(check(run(), "--rounds", str(CAPTURES / "absent.json")).returncode, 2)

    def test_an_ended_run_reports_its_record_and_is_otherwise_no_verdict(self):
        ended = 'error: "cancelled: superseded by new push"\n'
        for status in ("cancelled", "failed"):
            for record, code in (("", 2), (REASONED, 3), (UNAPPROVED, 1)):
                for error in (ended, ""):
                    with self.subTest(status=status, record=record, error=error):
                        done = check(run(record, outcome=status, status=status) + error)
                        self.assertEqual(done.returncode, code, done.stdout)
                        if code == 2:
                            self.assertIn(f"NO VERDICT: run 01EXAMPLE ({status}) ended {status}", done.stdout)

    def test_a_blank_reason_is_no_operator_reason(self):
        for value in ('""', '"live validation verdict: inconclusive\\nTest exception approved:"', '"Test exception approved:   "', '"Test exception approved: \\n"'):
            with self.subTest(value=value):
                done = check(run(f"  test_override_reason: {value}\n", outcome="passed-with-override"))
                self.assertEqual(done.returncode, 1, done.stdout)

    def test_a_record_field_with_no_value_is_unread(self):
        for record in ("  test_override_reason:\n", "  test_override_reason:   \n", '  "test_override_reason": "operator approved"\n'):
            with self.subTest(record=record):
                done = check(run(record, outcome="passed-with-override"))
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("unparsed Test exception", done.stdout)

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
                    text = run(parsed + record, outcome="passed-with-override")
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
        self.assertEqual(check(run(record, outcome="passed-with-override")).returncode, 1)

    def test_ci_override_alone_is_not_a_test_exception(self):
        done = check(run('ci_override_reason: "operator approved"\n', outcome="passed-with-override"))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_exception_words_in_another_field_value_are_not_a_record(self):
        for value in (
            "  branch: fix/test-exception\n",
            "current_branch: fix/test-override\n",
            "  summary: The Test exception path was exercised.\n",
            '  findings[1]{id,severity,file,action,description}:\n    review-1,warning,a.py,ask-user,"keys on a `test_override_reason:` line"\n',
        ):
            with self.subTest(value=value):
                done = check(run(value, outcome="passed"))
                self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_help_line_that_repeats_a_parsed_exception_keeps_its_verdict(self):
        repeat = 'help[1]: "Report the approved Test exception, not a clean Test pass: Test exception approved: {reason}"\n'
        for record, reason, code in ((REASONED, "The operator approved the pending live scenario.", 3), (UNAPPROVED, "no operator reason supplied", 1)):
            with self.subTest(code=code):
                done = check(run(record, outcome="checks-passed") + repeat.format(reason=reason))
                self.assertEqual(done.returncode, code, done.stdout)

    def test_an_exception_with_no_operator_reason_blocks(self):
        done = check(run(UNAPPROVED, outcome="passed-with-override"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stdout)
        self.assertIn("no operator reason supplied", done.stdout)

    def test_an_exception_with_a_reason_needs_a_match_and_never_passes(self):
        done = check(run(REASONED, outcome="passed-with-override"))
        self.assertEqual(done.returncode, 3)
        self.assertIn("The operator approved the pending live scenario.", done.stdout)
        self.assertIn("operator's own approval", done.stdout)

    def test_the_worst_record_decides_when_the_status_holds_several_runs(self):
        text = run(REASONED, outcome="passed-with-override") + run(UNAPPROVED, outcome="passed-with-override")
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
        self.assertEqual(check("error: daemon unavailable\n" + run("", outcome="passed")).returncode, 2)

    def test_empty_run_fields_cannot_borrow_the_next_lines_value(self):
        for field in ("id", "status", "head_sha"):
            for whitespace in ("", " ", "\t"):
                with self.subTest(field=field, whitespace=whitespace):
                    lines = [f"{name}: {value}" if name != field else f"{name}:{whitespace}"
                             for name, value in (("id", "01EXAMPLE"), ("status", "completed"), ("head_sha", "abcdef"))]
                    done = check("\n".join(lines) + "\noutcome: passed\n")
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertIn("UNREAD", done.stdout)

    def test_it_reads_a_file_and_reports_a_missing_one_as_unread(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "status.toon"
            saved.write_text(run(UNAPPROVED, outcome="passed-with-override"), encoding="utf-8")
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
