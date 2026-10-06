import json
import tempfile
import unittest
from pathlib import Path

from grade_boundary import GradeRefused
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


class CopyInto(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-copy-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.native = self.tmp / "native"
        self.native.mkdir()
        self.outside = self.tmp / "outside.jsonl"
        self.outside.write_bytes(b"outside marker\n")

    def test_source_link_is_refused_without_copying_outside_bytes(self):
        link = self.native / "rollout-a.jsonl"
        link.symlink_to(self.outside)
        with self.assertRaises(GradeRefused):
            codex.copy_into([link], self.tmp / "captured")
        self.assertEqual([p.read_bytes() for p in (self.tmp / "captured").glob("*")], [])

    def test_destination_link_is_refused_without_writing_outside(self):
        source = self.native / "rollout-a.jsonl"
        source.write_bytes(b"native rollout\n")
        captured = self.tmp / "captured"
        captured.mkdir()
        (captured / source.name).symlink_to(self.outside)
        with self.assertRaises(GradeRefused):
            codex.copy_into([source], captured)
        self.assertEqual(self.outside.read_bytes(), b"outside marker\n")

    def test_regular_rollout_is_copied(self):
        source = self.native / "rollout-a.jsonl"
        source.write_bytes(b"native rollout\n")
        copied = codex.copy_into([source], self.tmp / "captured")
        self.assertEqual(copied, [str(self.tmp / "captured" / "rollout-a.jsonl")])
        self.assertEqual(Path(copied[0]).read_bytes(), b"native rollout\n")


if __name__ == "__main__":
    unittest.main()
