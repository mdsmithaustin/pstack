import json
import tempfile
import unittest
from pathlib import Path

import report


class Render(unittest.TestCase):
    def test_a_promise_the_ledger_retired_still_renders_and_says_so(self):
        with tempfile.TemporaryDirectory() as out:
            run = Path(out) / "run"
            run.mkdir()
            (run / "verdict.json").write_text(json.dumps({
                "harness": "codex",
                "promises": {"a-promise-no-longer-in-the-ledger": {"verdict": "FAIL", "failures": ["x"], "evidence": []}}}))
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("| `a-promise-no-longer-in-the-ledger` |  | FAIL |  |  | retired |", table)

    def test_the_claude_skill_listing_state_of_each_run_is_counted(self):
        with tempfile.TemporaryDirectory() as out:
            for name, step in (("a", "installed"), ("b", "installed"), ("c", "absent"), ("d", None)):
                run = Path(out) / name
                run.mkdir()
                (run / "verdict.json").write_text(json.dumps({"harness": "claude-code", "promises": {}}))
                (run / "trace.json").write_text(json.dumps({"x_skill_listing": {"step": step, "name_only": []}} if step else {}))
            table = report.render(Path(out), upstream=Path(out))
        self.assertEqual(table.splitlines()[-1], "claude-code skill listing: absent 1, installed 2")

    def run_dir(self, out, name, harness, verdicts):
        run = Path(out) / name
        run.mkdir()
        (run / "verdict.json").write_text(json.dumps({"harness": harness, "promises": {
            pid: {"verdict": v, "failures": [], "evidence": []} for pid, v in verdicts.items()}}))

    def test_an_error_run_drops_out_of_the_pass_rate_and_keeps_its_cell(self):
        with tempfile.TemporaryDirectory() as out:
            self.run_dir(out, "a", "claude-code", {"p1": "PASS", "p2": "FAIL"})
            self.run_dir(out, "b", "claude-code", {"p1": "ERROR", "p2": "ERROR"})
            self.run_dir(out, "c", "claude-code", {"p3": "INCONCLUSIVE"})
            self.run_dir(out, "d", "codex", {"p1": "ERROR"})
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("claude-code pass rate: 1 of 3 (ERROR 2 excluded)", table)
        self.assertIn("codex pass rate: none graded (ERROR 1 excluded)", table)
        self.assertIn("| `p1` | ERROR 1, PASS 1 | ERROR |", table)
        self.assertIn("ERROR 3, FAIL 1, INCONCLUSIVE 1, PASS 1", table)

    def test_a_run_whose_transcript_could_not_be_read_counts_only_the_promises_that_apply(self):
        recorded = Path(__file__).resolve().parent / "testdata" / "harvest_refused" / "hermes-feature-run-verdict.json"
        with tempfile.TemporaryDirectory() as out:
            run = Path(out) / "tally"
            run.mkdir()
            (run / "verdict.json").write_bytes(recorded.read_bytes())
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("hermes pass rate: 0 of 10\n", table + "\n")
        self.assertIn("| `persona-delivery-hermes-grok` |  |  | INCONCLUSIVE |  |  |", table)
        self.assertNotIn("claude-effort-applies-via-effort-agents", table)

    def test_a_retained_hermes_pair_counts_its_run_once(self):
        with tempfile.TemporaryDirectory() as out:
            for rel in ("hermes/runs/tally-a", "hermes-retained/pair-1/run"):
                run = Path(out) / rel
                run.mkdir(parents=True)
                (run / "verdict.json").write_text(json.dumps({"harness": "hermes", "promises": {
                    "p1": {"verdict": "PASS", "failures": [], "evidence": []}}}))
                (run / "trace.json").write_text(json.dumps({"x_skill_listing": {"step": "installed"}}))
            pair = Path(out) / "hermes-retained" / "pair-1"
            (pair / "pair.json").write_text(json.dumps({"original_root": str(Path(out) / "hermes/runs/tally-a")}))
            for scope in (Path(out), pair.parent, pair):
                with self.subTest(scope=scope):
                    table = report.render(scope, upstream=Path(out))
                    self.assertIn("hermes pass rate: 1 of 1\n", table + "\n")
                    self.assertIn("| `p1` |  |  | PASS |  |", table)
                    self.assertIn("hermes skill listing: installed 1", table)

    def test_a_retained_hermes_pair_counts_when_its_original_run_is_missing(self):
        with tempfile.TemporaryDirectory() as out:
            pair = Path(out) / "hermes-retained" / "pair-1"
            pair.mkdir(parents=True)
            self.run_dir(pair, "run", "hermes", {"p1": "PASS"})
            (pair / "run" / "trace.json").write_text(json.dumps({"x_skill_listing": {"step": "installed"}}))
            (pair / "pair.json").write_text(json.dumps({"original_root": str(Path(out) / "hermes/runs/tally-a")}))
            for scope in (Path(out), pair.parent, pair):
                with self.subTest(scope=scope):
                    table = report.render(scope, upstream=Path(out))
                    self.assertIn("hermes pass rate: 1 of 1\n", table + "\n")
                    self.assertIn("hermes skill listing: installed 1", table)

    def test_a_run_directory_without_a_pair_beside_it_still_counts(self):
        with tempfile.TemporaryDirectory() as out:
            self.run_dir(out, "a", "grok", {"p1": "PASS"})
            (Path(out) / "b").mkdir()
            self.run_dir(Path(out) / "b", "run", "grok", {"p1": "FAIL"})
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("grok pass rate: 1 of 2\n", table + "\n")

    def test_a_harness_with_no_error_prints_a_plain_pass_rate(self):
        with tempfile.TemporaryDirectory() as out:
            self.run_dir(out, "a", "grok", {"p1": "PASS", "p2": "PASS", "p3": "FAIL"})
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("grok pass rate: 2 of 3\n", table + "\n")
        self.assertNotIn("excluded", table)


if __name__ == "__main__":
    unittest.main()
