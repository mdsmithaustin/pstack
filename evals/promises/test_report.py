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

    def test_a_harness_with_no_error_prints_a_plain_pass_rate(self):
        with tempfile.TemporaryDirectory() as out:
            self.run_dir(out, "a", "grok", {"p1": "PASS", "p2": "PASS", "p3": "FAIL"})
            table = report.render(Path(out), upstream=Path(out))
        self.assertIn("grok pass rate: 2 of 3\n", table + "\n")
        self.assertNotIn("excluded", table)


if __name__ == "__main__":
    unittest.main()
