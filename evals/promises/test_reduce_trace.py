import copy
import json
import unittest
from pathlib import Path

import reduce_trace

HERE = Path(__file__).resolve().parent
TRACES = HERE / "testdata" / "traces"
CASES = ("feature-run", "route-feature")
FIXTURE_BUDGET = 8192


def cases():
    return [reduce_trace.load_case(c) for c in CASES]


class ReduceTrace(unittest.TestCase):
    def test_junk_is_dropped_and_every_verdict_is_kept(self):
        trace = {"harness": "claude-code", "model": "m", "exit_code": 0, "entry": "injected", "cli_version": "9", "cost_usd": 1.5,
                 "cwd": "/Users/someone/project", "duration_s": 3,
                 "events": [{"seq": 0, "kind": "tool_call", "name": "Read", "input": {"file_path": "/w/.claude/skills/poteto-mode/playbooks/feature.md", "note": "x" * 300}},
                            {"seq": 1, "kind": "text", "text": "chatter " * 100}],
                 "worklist": [], "spawns": [], "files_read": [], "final_reply": "Done. " * 200}
        before = reduce_trace.fingerprint(trace, cases())
        reduced = reduce_trace.reduce_trace(copy.deepcopy(trace), cases())
        self.assertEqual(reduce_trace.fingerprint(reduced, cases()), before)
        self.assertLess(len(json.dumps(reduced)), len(json.dumps(trace)) // 4)
        for junk in ("cli_version", "cost_usd", "cwd", "duration_s"):
            self.assertNotIn(junk, reduced)

    def test_host_paths_are_rewritten(self):
        self.assertEqual(reduce_trace.sanitize({"a": ["/Users/alice/x", {"b": "/home/bob/y"}]}),
                         {"a": ["/Users/dev/x", {"b": "/home/dev/y"}]})

    def test_a_committed_fixture_stays_reduced(self):
        for path in sorted(TRACES.glob("*.json")):
            with self.subTest(trace=path.name):
                trace = json.loads(path.read_text(encoding="utf-8"))
                self.assertLess(path.stat().st_size, FIXTURE_BUDGET, f"{path.name} looks like a raw trace; run reduce_trace.py on it")
                self.assertEqual(sorted(set(trace) - {"harness", "model", "effort", "exit_code", "entry", "events", "files_read",
                                                      "worklist", "spawns", "final_reply", "x_subagents", "files_read_by"}), [])


if __name__ == "__main__":
    unittest.main()
