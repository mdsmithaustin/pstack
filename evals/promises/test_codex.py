import json
import tempfile
import unittest
from pathlib import Path

from harnesses import codex


class CallIds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-ids-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def lines(self, name, rows):
        path = self.tmp / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path

    def test_codex_tool_events_carry_the_call_id(self):
        def item(payload):
            return {"type": "response_item", "payload": payload}
        rows = [{"type": "session_meta", "payload": {"cwd": "/w", "id": "s"}},
                item({"type": "function_call", "name": "exec_command", "call_id": "x1", "arguments": json.dumps({"cmd": "a"})}),
                item({"type": "function_call", "name": "exec_command", "call_id": "x2", "arguments": json.dumps({"cmd": "b"})}),
                item({"type": "function_call_output", "call_id": "x2", "output": "Error: nope"}),
                item({"type": "function_call_output", "call_id": "x1", "output": "fine"})]
        parsed = codex.harvest_rollout(self.lines("rollout-s.jsonl", rows))
        self.assertEqual([(e["kind"], e.get("id"), e.get("ok")) for e in parsed["events"]],
                         [("tool_call", "x1", None), ("tool_call", "x2", None), ("tool_result", "x2", False), ("tool_result", "x1", True)])


if __name__ == "__main__":
    unittest.main()
