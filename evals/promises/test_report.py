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


if __name__ == "__main__":
    unittest.main()
