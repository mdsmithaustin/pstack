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


if __name__ == "__main__":
    unittest.main()
