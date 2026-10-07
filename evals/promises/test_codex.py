import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from grade_boundary import GradeRefused
from harnesses import codex


class CallIds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-ids-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

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


class HarvestCopies(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-codex-harvest-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "run"
        self.run_ = SimpleNamespace(root=root, project=root / "w" / "p", case={"turns": ["go"]},
                                    turns=[{"session_id": "lead", "argv": ["codex", "go"]}])
        store = root / "codex-home" / "sessions" / "2026"
        store.mkdir(parents=True)
        self.rollout = store / "rollout-x-lead.jsonl"
        self.rollout.write_text(self.reply("native reply"))
        (root / "launch.json").write_text(json.dumps({"path": "codex", "source": "test", "version": "test", "rejected": []}))

    def reply(self, text):
        return "".join(json.dumps(r) + "\n" for r in [
            {"type": "session_meta", "payload": {"id": "lead", "cwd": "/w"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                  "content": [{"type": "output_text", "text": text}]}}])

    def test_the_trace_is_parsed_from_the_bytes_the_copy_retained(self):
        copy = codex.copy_into

        def rewrite_then_copy(*args):
            self.rollout.write_text(self.reply("rewritten reply"))
            return copy(*args)

        with mock.patch.object(codex, "copy_into", side_effect=rewrite_then_copy):
            trace = codex.harvest(self.run_)
        retained = Path(trace["transcript_paths"][0]).read_text()
        self.assertEqual((trace["final_reply"], retained), ("native reply", self.reply("native reply")))


class FindRollouts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-find-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.store = self.tmp / "sessions" / "2026"
        self.store.mkdir(parents=True)
        self.lead = self.rollout(self.store / "rollout-a-lead.jsonl", {"id": "lead"})
        self.outside = self.rollout(self.tmp / "outside.jsonl", {"id": "kid", "parent_thread_id": "lead"})
        (self.tmp / "outside-directory").mkdir()

    def rollout(self, path, meta):
        path.write_text(json.dumps({"type": "session_meta", "payload": meta}) + "\n")
        return path

    def test_linked_rollout_is_refused_before_discovery_reads_it(self):
        self.assertEqual(codex.find_rollouts(self.store, {"lead"}), ([self.lead], []))
        link = self.store / "rollout-b-kid.jsonl"
        for target in (self.outside, self.tmp / "missing", self.tmp / "outside-directory"):
            with self.subTest(target=target.name):
                link.unlink(missing_ok=True)
                link.symlink_to(target)
                with self.assertRaises(GradeRefused):
                    codex.find_rollouts(self.store, {"lead"})

    def test_linked_directory_in_the_store_is_refused(self):
        linked = self.tmp / "outside-directory"
        self.rollout(linked / "rollout-z.jsonl", {"id": "kid", "parent_thread_id": "lead"})
        (self.store / "linkdir").symlink_to(linked, target_is_directory=True)
        with self.assertRaises(GradeRefused) as refused:
            codex.find_rollouts(self.store, {"lead"})
        self.assertEqual(refused.exception.receipt,
                         {"run_id": None, "reason": "unsafe_link", "detail": str(self.store / "linkdir")})


if __name__ == "__main__":
    unittest.main()
