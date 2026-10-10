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
        parsed = codex.harvest_rollout(self.lines("rollout-s.jsonl", rows).read_bytes())
        self.assertEqual([(e["kind"], e.get("id"), e.get("ok")) for e in parsed["events"]],
                         [("tool_call", "x1", None), ("tool_call", "x2", None), ("tool_result", "x2", False), ("tool_result", "x1", True)])


class Compaction(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-codex-compact-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        (root / "transcripts").mkdir()
        (root / "launch.json").write_text(json.dumps({"path": "codex", "source": "test", "version": "test", "rejected": []}))
        self.run_ = SimpleNamespace(root=root, project=root / "w" / "relay", model=None, effort=None, timeout_s=60,
                                    case={"id": "c", "turns": ["what does relay do?", "/compact"]},
                                    turns=[{"index": 0, "session_id": "thread-1", "argv": ["codex", "what does relay do?"]}])

    def test_a_compact_turn_resumes_with_a_small_auto_compact_limit(self):
        def execute(argv, cwd, env, timeout_s, stdout, stderr):
            stdout.write_text("")
            return {"argv": [str(a) for a in argv], "exit_code": 0, "timed_out": False, "duration_s": 1.0}
        with mock.patch.object(codex.live, "execute", side_effect=execute):
            record = codex.turn(self.run_, "/compact", 1)
        argv = record["argv"]
        self.assertEqual(argv[1:3], ["exec", "resume"])
        self.assertEqual(argv[argv.index("model_auto_compact_token_limit=2000") - 1], "-c")
        self.assertEqual(argv[-3:], ["--", "thread-1", "/compact"])
        self.assertEqual(record["session_id"], "thread-1")
        with mock.patch.object(codex.live, "execute", side_effect=execute):
            later = codex.turn(self.run_, "what does relay do?", 1)["argv"]
        self.assertNotIn("model_auto_compact_token_limit=2000", later)

    def test_a_first_turn_cannot_compact(self):
        with self.assertRaisesRegex(ValueError, "a /compact turn needs an earlier turn to compact"):
            codex.turn(self.run_, "/compact", 0)

    def test_the_rollout_compaction_record_is_stamped_with_the_turn_it_opened(self):
        def message(role, text):
            return {"type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]}}
        rows = [{"type": "session_meta", "payload": {"cwd": "/w", "id": "thread-1"}},
                {"type": "event_msg", "payload": {"type": "task_started"}}, message("user", "what does relay do?"),
                message("assistant", "It imports feeds."), {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "compacted", "ordinal": 33, "payload": {"message": "", "replacement_history": []}},
                {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "ContextCompaction", "id": "k"}}},
                message("user", "/compact"), message("assistant", "Compacted.")]
        data = "".join(json.dumps(r) + "\n" for r in rows).encode()
        lead = codex.harvest_rollout(data, ["what does relay do?", "/compact"])
        self.assertEqual(lead["compactions"], [{"turn": 1, "ordinal": 33, "source": "rollout"}])
        self.assertEqual([(e["turn"], e["kind"]) for e in lead["events"] if e["kind"] in ("user", "text")],
                         [(0, "user"), (0, "text"), (1, "user"), (1, "text")])
        self.assertEqual(codex.harvest_rollout(data)["compactions"], [{"turn": None, "ordinal": 33, "source": "rollout"}])


class CopyInto(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-copy-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.source = self.tmp / "native" / "rollout-a.jsonl"
        self.outside = self.tmp / "outside.jsonl"
        self.outside.write_bytes(b"outside marker\n")

    def test_destination_link_is_refused_without_writing_outside(self):
        captured = self.tmp / "captured"
        captured.mkdir()
        (captured / self.source.name).symlink_to(self.outside)
        with self.assertRaises(GradeRefused):
            codex.copy_into({self.source: b"native rollout\n"}, captured)
        self.assertEqual(self.outside.read_bytes(), b"outside marker\n")

    def test_regular_rollout_is_copied(self):
        copied = codex.copy_into({self.source: b"native rollout\n"}, self.tmp / "captured")
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
        self.rollouts = {"lead": store / "rollout-x-lead.jsonl", "kid": store / "rollout-y-kid.jsonl"}
        self.write("native")
        (root / "launch.json").write_text(json.dumps({"path": "codex", "source": "test", "version": "test", "rejected": []}))

    def write(self, version):
        for thread, path in self.rollouts.items():
            meta = {"id": thread, "cwd": "/w", **({"parent_thread_id": "lead"} if thread == "kid" else {})}
            path.write_text("".join(json.dumps(r) + "\n" for r in [
                {"type": "session_meta", "payload": meta},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                      "content": [{"type": "output_text", "text": f"{version} {thread} reply"}]}}]))

    def retained_reply(self, trace, thread):
        path = next(Path(p) for p in trace["transcript_paths"] if Path(p).name == self.rollouts[thread].name)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        return rows[-1]["payload"]["content"][0]["text"]

    def test_the_trace_matches_the_retained_rollouts_when_natives_change_around_the_copy(self):
        copy = codex.copy_into

        def rewrite_around_copy(*args):
            self.write("before-copy")
            copied = copy(*args)
            self.write("after-copy")
            return copied

        with mock.patch.object(codex, "copy_into", side_effect=rewrite_around_copy):
            trace = codex.harvest(self.run_)
        self.assertEqual((trace["final_reply"], [s["final_reply"] for s in trace["x_subagents"]]),
                         (self.retained_reply(trace, "lead"), [self.retained_reply(trace, "kid")]))

    def test_harvest_refuses_a_linked_or_vanished_turn_stream(self):
        outside = self.run_.root / "outside.jsonl"
        outside.write_text(json.dumps({"type": "item.completed", "item": {"type": "todo_list", "items": []}}) + "\n")
        stream = self.run_.root / "transcripts" / "turn-0.jsonl"
        stream.parent.mkdir()
        self.run_.turns[0]["stream"] = str(stream)
        for plant, reason in ((lambda: stream.symlink_to(outside), "unsafe_link"),
                              (lambda: stream.symlink_to(self.run_.root / "missing"), "unsafe_link"),
                              (lambda: None, "input_changed")):
            with self.subTest(reason=reason):
                stream.unlink(missing_ok=True)
                plant()
                with self.assertRaises(GradeRefused) as refused:
                    codex.harvest(self.run_)
                self.assertEqual(refused.exception.receipt["reason"], reason)


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
        self.assertEqual(codex.find_rollouts(self.store, {"lead"}), ({self.lead: self.lead.read_bytes()}, {}))
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
