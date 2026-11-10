import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODE = Path(__file__).resolve().parents[1] / "skills/poteto-mode"
SCRIPT = MODE / "scripts/second-opinion.py"
PLAN = MODE / "scripts/plan.py"
LOW = ["--consequence", "low:a", "--reach", "low:b", "--uncertainty", "low:c", "--complexity", "low:d", "--reversibility", "low:e"]
ALL_LOW = {"consequence": "low", "reach": "low", "uncertainty": "low", "complexity": "low", "reversibility": "low"}


class SecondOpinion(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.out = self.project / "answer.json"

    def switch(self, cli):
        (self.project / ".agents").mkdir(exist_ok=True)
        (self.project / ".agents/pstack-second-opinion").write_text(cli + "\n")

    def fake(self, name, body):
        tool = self.project / name
        tool.write_text("#!/bin/sh\n" + body)
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        return str(tool)

    def ask(self, executable=None):
        argv = [sys.executable, str(SCRIPT), "--task", "add a flag", *LOW, "--project", str(self.project), "--out", str(self.out)]
        if executable:
            argv += ["--executable", executable, "--timeout", "20"]
        done = subprocess.run(argv, capture_output=True, text=True)
        return done.returncode, json.loads(done.stdout)

    def plan(self, *extra):
        done = subprocess.run([sys.executable, str(PLAN), "feature", *LOW, "--json", "--project", str(self.project), *extra],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_it_is_off_until_the_repository_turns_it_on(self):
        code, result = self.ask()
        self.assertEqual((code, result["status"]), (3, "off"))
        self.assertFalse(self.out.exists())

    def test_claude_answer_is_written_for_plan(self):
        self.switch("claude")
        answer = json.dumps({**ALL_LOW, "reach": "material"})
        record = json.dumps({"type": "result", "is_error": False, "result": answer})
        tool = self.fake("claude", f"cat >/dev/null\nprintf '%s' '{record}'\n")
        code, result = self.ask(tool)
        self.assertEqual((code, result["status"], result["levels"]["reach"]), (0, "answered", "material"))
        merged = self.plan("--second-opinion", str(self.out))
        self.assertEqual(merged["route"], "standard")
        self.assertEqual(merged["facts"]["reach"]["level"], "material")
        self.assertIn("second opinion raised: reach", merged["second_opinion"])

    def test_codex_answer_is_read_from_its_event_stream(self):
        self.switch("codex")
        answer = json.dumps({**ALL_LOW, "consequence": "unknown"})
        events = "\n".join(json.dumps(event) for event in (
            {"type": "item.completed", "item": {"type": "agent_message", "text": answer}}, {"type": "turn.completed"}))
        tool = self.fake("codex", f"if [ \"$1\" = mcp ]; then echo '[]'; exit 0; fi\ncat >/dev/null\ncat <<'END'\n{events}\nEND\n")
        code, result = self.ask(tool)
        self.assertEqual((code, result["levels"]["consequence"]), (0, "unknown"))

    def test_a_codex_tool_event_makes_the_answer_unavailable(self):
        self.switch("codex")
        events = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
        tool = self.fake("codex", f"if [ \"$1\" = mcp ]; then echo '[]'; exit 0; fi\ncat >/dev/null\necho '{events}'\n")
        code, result = self.ask(tool)
        self.assertEqual((code, result["status"]), (1, "unavailable"))
        self.assertFalse(self.out.exists())

    def test_malformed_and_failed_answers_are_unavailable(self):
        self.switch("claude")
        for body in ("cat >/dev/null\necho 'not json'\n", "cat >/dev/null\nexit 4\n",
                     "cat >/dev/null\nprintf '%s' '{\"type\":\"result\",\"is_error\":false,\"result\":\"{\\\"reach\\\":\\\"low\\\"}\"}'\n"):
            with self.subTest(body=body):
                code, result = self.ask(self.fake("claude", body))
                self.assertEqual((code, result["status"]), (1, "unavailable"))

    def test_an_earlier_answer_is_removed_before_each_run(self):
        self.out.write_text(json.dumps({"status": "answered", "cli": "codex", "levels": {**ALL_LOW, "reach": "material"}}))
        code, _ = self.ask()
        self.assertEqual(code, 3)
        self.assertFalse(self.out.exists())
        self.switch("claude")
        self.out.write_text(json.dumps({"status": "answered", "cli": "codex", "levels": {**ALL_LOW, "reach": "material"}}))
        code, _ = self.ask(self.fake("claude", "cat >/dev/null\nexit 4\n"))
        self.assertEqual(code, 1)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.plan("--second-opinion", str(self.out))["route"], "lightweight")

    def test_a_second_opinion_never_lowers_a_fact(self):
        self.out.write_text(json.dumps({"status": "answered", "cli": "codex", "levels": ALL_LOW}))
        done = subprocess.run([sys.executable, str(PLAN), "feature", "--consequence", "low:a", "--reach", "material:12 callers",
                               "--uncertainty", "low:c", "--complexity", "low:d", "--reversibility", "low:e", "--json",
                               "--project", str(self.project), "--second-opinion", str(self.out)], capture_output=True, text=True)
        merged = json.loads(done.stdout)
        self.assertEqual((merged["route"], merged["facts"]["reach"]["level"]), ("standard", "material"))

    def test_a_bad_answer_file_leaves_the_table_result(self):
        self.out.write_text(json.dumps({"status": "unavailable"}))
        merged = self.plan("--second-opinion", str(self.out))
        self.assertEqual(merged["route"], "lightweight")
        self.assertIn("second opinion ignored", merged["second_opinion"])
        self.assertEqual(self.plan("--second-opinion", str(self.project / "missing.json"))["route"], "lightweight")


if __name__ == "__main__":
    unittest.main()
