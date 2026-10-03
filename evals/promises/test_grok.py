import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harnesses import grok


class CallIds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-ids-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def lines(self, name, rows):
        path = self.tmp / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path

    def test_grok_tool_events_carry_the_call_id(self):
        rows = [{"type": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "name": "run_terminal_command", "arguments": json.dumps({"command": "a"})},
            {"id": "t2", "name": "run_terminal_command", "arguments": json.dumps({"command": "b"})}]},
                {"type": "tool_result", "tool_call_id": "t2", "content": "Error: nope"},
                {"type": "tool_result", "tool_call_id": "t1", "content": "fine"}]
        parsed = grok.parse_session(self.lines("chat_history.jsonl", rows), "/w", None)
        self.assertEqual([(e["kind"], e.get("id"), e.get("ok")) for e in parsed["events"]],
                         [("tool_call", "t1", None), ("tool_call", "t2", None), ("tool_result", "t2", False), ("tool_result", "t1", True)])


if __name__ == "__main__":
    unittest.main()
