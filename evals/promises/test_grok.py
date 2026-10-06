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

    def test_session_files_and_subagent_meta_are_copied(self):
        self.chat.write_bytes(b"native transcript\n")
        (self.session / "subagents" / "kid").mkdir(parents=True)
        (self.session / "subagents" / "kid" / "meta.json").write_bytes(b"{}")
        target = self.captured / "cwd" / "session"
        self.assertEqual(grok.copy_session(self.session, self.captured),
                         [str(target / "chat_history.jsonl"), str(target / "subagents" / "kid" / "meta.json")])
        self.assertEqual((target / "chat_history.jsonl").read_bytes(), b"native transcript\n")


if __name__ == "__main__":
    unittest.main()
