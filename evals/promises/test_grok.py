import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from grade_boundary import GradeRefused
from harnesses import grok


class GrokHome(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-grok-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.host = self.tmp / "host"
        self.host.mkdir()
        (self.host / ".gitconfig").write_text("[user]\n\tname = Real Person\n[commit]\n\tgpgsign = true\n")
        (self.host / ".zshrc").write_text("export PATH=/opt/tools:$PATH\n")
        for name in (".config", ".local", ".cache", ".npm"):
            (self.host / name).mkdir()
            (self.host / name / "secret").write_text("token")
        (self.host / ".grok").mkdir()
        (self.host / ".grok" / "auth.json").write_text(json.dumps({"x": {"key": "k", "expires_at": "2999-01-01T00:00:00Z"}}))
        self.root = self.tmp / "run"
        self.root.mkdir()
        (self.root / "w").mkdir()
        self.run_ = SimpleNamespace(root=self.root, project=self.root / "w" / "p", case={"turns": ["go"]})
        self.run_.project.mkdir()

    def prepare(self):
        def fake(argv, **kwargs):
            if "inspect" in argv:
                return subprocess.CompletedProcess(argv, 0, json.dumps({"grokVersion": "9", "skills": []}), "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(grok, "host_home", return_value=self.host), \
                mock.patch.object(grok, "host_grok_home", return_value=self.host / ".grok"), \
                mock.patch.object(grok, "resolve_binary", return_value={"source": "t", "path": "/bin/grok", "version": "9", "rejected": []}), \
                mock.patch.object(grok.subprocess, "run", side_effect=fake):
            grok.prepare(self.run_)
        return self.root / "home"

    def test_the_run_home_holds_no_link_into_the_host_home(self):
        home = self.prepare()
        links = sorted(p.name for p in home.iterdir() if p.is_symlink())
        self.assertEqual(links, [])

    def test_writes_in_the_run_home_never_reach_the_host(self):
        home = self.prepare()
        with open(home / ".gitconfig", "a") as handle:
            handle.write("\n# agent\n")
        (home / ".config").mkdir(exist_ok=True)
        (home / ".config" / "new").write_text("x")
        self.assertNotIn("agent", (self.host / ".gitconfig").read_text())
        self.assertFalse((self.host / ".config" / "new").exists())

    def test_host_credentials_and_signing_settings_are_not_copied_in(self):
        home = self.prepare()
        self.assertFalse((home / ".config" / "secret").exists())
        self.assertFalse((home / ".local" / "secret").exists())
        self.assertNotIn("gpgsign = true", (home / ".gitconfig").read_text())


class CallIds(unittest.TestCase):
    def test_grok_tool_events_carry_the_call_id(self):
        rows = [{"type": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "name": "run_terminal_command", "arguments": json.dumps({"command": "a"})},
            {"id": "t2", "name": "run_terminal_command", "arguments": json.dumps({"command": "b"})}]},
                {"type": "tool_result", "tool_call_id": "t2", "content": "Error: nope"},
                {"type": "tool_result", "tool_call_id": "t1", "content": "fine"}]
        parsed = grok.parse_session("".join(json.dumps(r) + "\n" for r in rows).encode(), "/w", None)
        self.assertEqual([(e["kind"], e.get("id"), e.get("ok")) for e in parsed["events"]],
                         [("tool_call", "t1", None), ("tool_call", "t2", None), ("tool_result", "t2", False), ("tool_result", "t1", True)])


class CopySession(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-grok-copy-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.session = self.tmp / "native" / "cwd" / "session"
        self.session.mkdir(parents=True)
        self.captured = self.tmp / "captured"
        self.captured.mkdir()
        self.outside = self.tmp / "outside-marker"
        self.outside.write_bytes(b"outside marker\n")
        self.chat = self.session / "chat_history.jsonl"

    def test_source_link_is_refused_without_copying_outside_bytes(self):
        self.chat.symlink_to(self.outside)
        with self.assertRaises(GradeRefused):
            grok.copy_session(self.session, self.captured)
        self.assertEqual([p.read_bytes() for p in self.captured.rglob("*") if p.is_file()], [])

    def test_dangling_or_directory_source_link_is_refused(self):
        self.chat.write_bytes(b"native transcript\n")
        (self.tmp / "outside-directory").mkdir()
        for target in (self.tmp / "missing", self.tmp / "outside-directory"):
            with self.subTest(target=target.name):
                events = self.session / "events.jsonl"
                events.unlink(missing_ok=True)
                events.symlink_to(target)
                with self.assertRaises(GradeRefused):
                    grok.copy_session(self.session, self.captured)

    def test_destination_file_link_is_refused_without_writing_outside(self):
        self.chat.write_bytes(b"native transcript\n")
        (self.captured / "cwd" / "session").mkdir(parents=True)
        (self.captured / "cwd" / "session" / self.chat.name).symlink_to(self.outside)
        with self.assertRaises(GradeRefused):
            grok.copy_session(self.session, self.captured)
        self.assertEqual(self.outside.read_bytes(), b"outside marker\n")

    def test_destination_directory_link_is_refused_without_creating_outside(self):
        self.chat.write_bytes(b"native transcript\n")
        external = self.tmp / "outside-directory"
        external.mkdir()
        (self.captured / "cwd").symlink_to(external, target_is_directory=True)
        with self.assertRaises(GradeRefused):
            grok.copy_session(self.session, self.captured)
        self.assertEqual(list(external.iterdir()), [])

    def test_a_chat_that_vanishes_between_the_exists_check_and_the_read_is_refused(self):
        self.chat.write_bytes(b"native transcript\n")
        with mock.patch.object(grok, "copy_file", side_effect=FileNotFoundError(self.chat)), \
                self.assertRaises(GradeRefused) as refused:
            grok.copy_session(self.session, self.captured)
        self.assertEqual(refused.exception.receipt["reason"], "input_changed")

    def test_a_non_chat_file_that_vanishes_before_its_copy_is_refused(self):
        self.chat.write_bytes(b"native transcript\n")
        (self.session / "usage.json").write_bytes(b"{}")
        (self.session / "subagents" / "kid").mkdir(parents=True)
        (self.session / "subagents" / "kid" / "meta.json").write_bytes(b"{}")
        copy = grok.copy_file
        for name in ("usage.json", "meta.json"):
            def vanish(source, target):
                if source.name == name:
                    raise FileNotFoundError(source)
                return copy(source, target)
            with self.subTest(name=name):
                with mock.patch.object(grok, "copy_file", side_effect=vanish), self.assertRaises(GradeRefused) as refused:
                    grok.copy_session(self.session, self.captured)
                self.assertEqual(refused.exception.receipt["reason"], "input_changed")

    def test_session_files_and_subagent_meta_are_copied(self):
        self.chat.write_bytes(b"native transcript\n")
        (self.session / "subagents" / "kid").mkdir(parents=True)
        (self.session / "subagents" / "kid" / "meta.json").write_bytes(b"{}")
        target = self.captured / "cwd" / "session"
        self.assertEqual(grok.copy_session(self.session, self.captured),
                         {target / "chat_history.jsonl": b"native transcript\n", target / "subagents" / "kid" / "meta.json": b"{}"})
        self.assertEqual((target / "chat_history.jsonl").read_bytes(), b"native transcript\n")


class HarvestCaptures(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-grok-harvest-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        root = self.tmp / "run"
        self.run_ = SimpleNamespace(root=root, project=root / "w" / "p", case={"turns": ["go"]},
                                    turns=[{"session_id": "lead", "argv": ["/bin/grok", "-p", "go"]}])
        sessions = root / "grok-home" / "sessions" / "cwd"
        self.lead = sessions / "lead"
        self.chat = self.lead / "chat_history.jsonl"
        self.meta = self.lead / "subagents" / "kid" / "meta.json"
        self.meta.parent.mkdir(parents=True)
        (sessions / "kid").mkdir()
        (sessions / "kid" / "chat_history.jsonl").write_text(json.dumps({"type": "assistant", "content": "kid reply"}) + "\n")
        self.chat.write_text(json.dumps({"type": "assistant", "content": "native reply"}) + "\n")
        self.meta.write_text(json.dumps({"child_session_id": "kid", "description": "native kid"}))
        canary = str(self.tmp / "host" / ".claude" / "skills")
        self.outside_chat = self.tmp / "outside-chat.jsonl"
        self.outside_chat.write_text(json.dumps({"type": "assistant", "content": f"outside reply {canary}"}) + "\n")
        self.outside_kid_chat = self.tmp / "outside-kid-chat.jsonl"
        self.outside_kid_chat.write_text(json.dumps({"type": "assistant", "content": "outside kid reply"}) + "\n")
        self.outside_meta = self.tmp / "outside-meta.json"
        self.outside_meta.write_text(json.dumps({"child_session_id": "kid", "description": "outside kid"}))

    def test_harvest_parses_the_copies_when_native_files_become_links(self):
        copy = grok.copy_session

        def copy_then_swap(session_dir, destination):
            copied = copy(session_dir, destination)
            for native, outside in ((self.chat, self.outside_chat), (self.meta, self.outside_meta)):
                if not native.is_symlink():
                    native.unlink()
                    native.symlink_to(outside)
            return copied

        with mock.patch.object(grok, "copy_session", side_effect=copy_then_swap), \
                mock.patch.object(grok, "host_home", return_value=self.tmp / "host"):
            trace = grok.harvest(self.run_)
        self.assertEqual((trace["final_reply"], [s["description"] for s in trace["x_subagents"]]),
                         ("native reply", ["native kid"]))

    def test_harvest_reads_only_the_files_it_copied(self):
        self.meta.unlink()
        outside_usage = self.tmp / "outside-usage.json"
        outside_usage.write_text(json.dumps({"session": {"costUsdTicks": 10 ** 10}}))
        planted = self.run_.root / "transcripts" / "sessions" / "cwd" / "lead"
        (planted / "subagents" / "planted").mkdir(parents=True)
        (planted / "usage.json").symlink_to(outside_usage)
        (planted / "subagents" / "planted" / "meta.json").symlink_to(self.outside_meta)
        with mock.patch.object(grok, "host_home", return_value=self.tmp / "host"):
            trace = grok.harvest(self.run_)
        self.assertEqual((trace["x_cost_usd_lead"], [s["description"] for s in trace["x_subagents"]]), (0, [None]))

    def harvest_with_stream(self, plant):
        stream = self.run_.root / "transcripts" / "turn-0.json"
        stream.parent.mkdir(parents=True, exist_ok=True)
        plant(stream)
        self.run_.turns[0]["stream"] = str(stream)
        with mock.patch.object(grok, "host_home", return_value=self.tmp / "host"):
            return grok.harvest(self.run_)

    def test_harvest_reads_a_regular_turn_stream_for_host_skill_hits(self):
        trace = self.harvest_with_stream(lambda stream: stream.write_bytes(self.outside_chat.read_bytes()))
        self.assertEqual((trace["x_host_skill_hits"], trace["transcript_paths"][-1]),
                         ([str(self.tmp / "host" / ".claude" / "skills")], self.run_.turns[0]["stream"]))

    def test_harvest_refuses_a_turn_stream_link_without_reading_its_target(self):
        for target in (self.outside_chat, self.tmp / "missing"):
            with self.subTest(target=target.name):
                with self.assertRaises(GradeRefused) as refused:
                    self.harvest_with_stream(lambda stream: (stream.unlink(missing_ok=True), stream.symlink_to(target)))
                self.assertEqual(refused.exception.receipt["reason"], "unsafe_link")

    def test_harvest_refuses_a_turn_stream_that_vanished(self):
        with self.assertRaises(GradeRefused) as refused:
            self.harvest_with_stream(lambda stream: None)
        self.assertEqual(refused.exception.receipt["reason"], "input_changed")

    def test_harvest_refuses_a_dangling_lead_chat(self):
        self.chat.unlink()
        self.chat.symlink_to(self.tmp / "missing")
        with mock.patch.object(grok, "host_home", return_value=self.tmp / "host"), \
                self.assertRaises(GradeRefused) as refused:
            grok.harvest(self.run_)
        self.assertEqual(refused.exception.receipt["reason"], "unsafe_link")

    def vanish_before_copy(self, session):
        native = self.lead.parent / session / "chat_history.jsonl"
        stale = self.run_.root / "transcripts" / "sessions" / "cwd" / session / "chat_history.jsonl"
        stale.parent.mkdir(parents=True)
        stale.write_text(json.dumps({"type": "assistant", "content": "stale capture"}) + "\n")
        listing = grok.session_files

        def list_then_vanish(run):
            found = listing(run)
            native.unlink()
            return found

        with mock.patch.object(grok, "session_files", side_effect=list_then_vanish), \
                mock.patch.object(grok, "host_home", return_value=self.tmp / "host"), \
                self.assertRaises(GradeRefused) as refused:
            grok.harvest(self.run_)
        self.assertEqual(refused.exception.receipt["reason"], "input_changed")

    def test_a_lead_whose_native_chat_vanishes_before_the_copy_is_refused(self):
        self.vanish_before_copy("lead")

    def test_a_child_whose_native_chat_vanishes_before_the_copy_is_refused(self):
        self.vanish_before_copy("kid")

    def change_captures_after_copy(self, change):
        self.lead.joinpath("usage.json").write_text(json.dumps({"session": {"costUsdTicks": 2 * 10 ** 8}}))
        outside_usage = self.tmp / "outside-usage.json"
        outside_usage.write_text(json.dumps({"session": {"costUsdTicks": 10 ** 10}}))
        copy = grok.copy_session
        swaps = {"lead": (("chat_history.jsonl", self.outside_chat), ("usage.json", outside_usage),
                          ("subagents/kid/meta.json", self.outside_meta)),
                 "kid": (("chat_history.jsonl", self.outside_kid_chat),)}

        def copy_then_change(session_dir, destination):
            copied = copy(session_dir, destination)
            target = destination / session_dir.parent.name / session_dir.name
            for name, outside in swaps.get(session_dir.name, ()):
                change(target / name, outside)
            return copied

        with mock.patch.object(grok, "copy_session", side_effect=copy_then_change), \
                mock.patch.object(grok, "host_home", return_value=self.tmp / "host"):
            trace = grok.harvest(self.run_)
        self.assertEqual((trace["final_reply"], trace["x_cost_usd_lead"], [(s["description"], s["final_reply"]) for s in trace["x_subagents"]],
                          trace["x_host_skill_hits"]),
                         ("native reply", 0.02, [("native kid", "kid reply")], []))

    def test_harvest_never_follows_a_capture_linked_out_after_the_copy(self):
        def link(path, outside):
            path.unlink()
            path.symlink_to(outside)
        self.change_captures_after_copy(link)

    def test_harvest_never_rereads_a_capture_rewritten_after_the_copy(self):
        self.change_captures_after_copy(lambda path, outside: path.write_bytes(outside.read_bytes()))


if __name__ == "__main__":
    unittest.main()
