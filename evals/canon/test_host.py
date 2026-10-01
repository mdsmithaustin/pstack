import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("canon_screen", ROOT / "screen.py")
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)

import host  # noqa: E402

EXPANSION = {"type": "user", "message": {"role": "user", "content": "<command-message>poteto-mode</command-message>\n<command-name>/poteto-mode</command-name>"}}
INJECTION = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "<skill>\n<name>poteto-mode</name>\n<path>/ws/.agents/skills/poteto-mode/SKILL.md</path>\n"}]}}

# A claude that persists its session under CLAUDE_CONFIG_DIR as Claude Code
# does: the transcript and a subagents dir named by --session-id, the init
# event listing the skills FAKE_SKILLS names.
FAKE_CLAUDE = f"""import json, os, pathlib, sys
argv = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode()
session = argv[argv.index("--session-id") + 1]
project = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / os.environ.get("FAKE_PROJECT", "-ws")
(project / "memory").mkdir(parents=True, exist_ok=True)
(project / session / "subagents").mkdir(parents=True)
(project / session / "subagents" / "agent-a1.jsonl").write_text("{{}}\\n")
(project / (session + ".jsonl")).write_text(json.dumps({EXPANSION!r}) + "\\n" + json.dumps({{"prompt": prompt}}) + "\\n")
skills = os.environ.get("FAKE_SKILLS", "poteto-mode").split(",")
print(json.dumps({{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": session, "skills": skills, "slash_commands": skills}}))
print(json.dumps({{"type": "result", "result": "done", "argv": argv, "prompt": prompt}}))
"""

# A codex that announces its thread and persists its rollout under CODEX_HOME,
# plus the rollout of a delegate it spawned, whose session_meta names it.
FAKE_CODEX = f"""import json, os, pathlib, sys
prompt = sys.stdin.buffer.read().decode()
thread = "0f0f0f0f-aaaa-bbbb-cccc-000000000001"
child = "0f0f0f0f-aaaa-bbbb-cccc-000000000002"
sessions = pathlib.Path(os.environ["CODEX_HOME"]) / "sessions" / "2026" / "09" / "30"
sessions.mkdir(parents=True, exist_ok=True)
(sessions / ("rollout-2026-09-30T00-00-00-" + thread + ".jsonl")).write_text(
    json.dumps({{"type": "session_meta", "payload": {{"id": thread, "session_id": thread}}}}) + "\\n" + json.dumps({INJECTION!r}) + "\\n")
(sessions / ("rollout-2026-09-30T00-00-01-" + child + ".jsonl")).write_text(
    json.dumps({{"type": "session_meta", "payload": {{"id": child, "parent_thread_id": thread, "agent_role": "poteto-agent"}}}}) + "\\n")
print(json.dumps({{"type": "thread.started", "thread_id": thread}}))
print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": prompt}}}}))
print(json.dumps({{"type": "turn.completed", "argv": sys.argv[1:]}}))
"""

SILENT = "import sys\nsys.stdin.buffer.read()\n"

# A claude that persists its session as FAKE_CLAUDE does and then never
# exits, which is how a run the harness times out looks from outside.
SLEEPING_CLAUDE = FAKE_CLAUDE + "sys.stdout.flush()\nimport time\ntime.sleep(60)\n"


class KeepSessionTests(unittest.TestCase):
    def test_claude_loses_the_persistence_flag_and_gets_a_session_id(self):
        command, session = host.keep_session("claude", ["claude", "-p", "--no-session-persistence", "--model", "sonnet"])

        self.assertEqual(str(uuid.UUID(session)), session)
        self.assertEqual(command, ["claude", "-p", "--model", "sonnet", "--session-id", session])

    def test_codex_loses_ephemeral_and_names_its_thread_itself(self):
        self.assertEqual(host.keep_session("codex", ["codex", "exec", "--json", "--ephemeral", "-"]), (["codex", "exec", "--json", "-"], None))


class HostWrapTests(unittest.TestCase):
    """host.py wrap in a harness-shaped workspace, with a fake agent that keeps
    its session the way the real one does, then screen.py's harvest move and
    exposure over the result."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name).resolve()
        self.ws = self.base / "ws"
        (self.ws / "skills" / "pstack" / "poteto-mode").mkdir(parents=True)
        (self.ws / "skills" / "pstack" / "poteto-mode" / "SKILL.md").write_text("# Poteto mode\n")
        self.work = self.base / "claude" / "rule" / "case" / "current"
        self.claude_home, self.codex_home = self.base / "claude-home", self.base / "codex-home"
        (self.claude_home / "projects" / "-ws").mkdir(parents=True)
        (self.claude_home / "projects" / "-ws" / "other.jsonl").write_text("{}\n")
        (self.codex_home / "sessions" / "2026" / "09" / "29").mkdir(parents=True)
        (self.codex_home / "sessions" / "2026" / "09" / "29" / "rollout-2026-09-29T00-00-00-other.jsonl").write_text("{}\n")
        environment = {"CANON_HARVEST": str(self.work / "harvest"), "CLAUDE_CONFIG_DIR": str(self.claude_home), "CODEX_HOME": str(self.codex_home)}
        patch = mock.patch.dict(os.environ, environment)
        patch.start()
        self.addCleanup(patch.stop)

    def wrap(self, agent, fake, *agent_args, **env):
        token, discovery = screen.ENTRY_INVOCATION[agent]
        script = self.base / f"{agent}.py"
        script.write_text(fake)
        stream = io.BytesIO()
        previous = Path.cwd()
        os.chdir(self.ws)
        try:
            with mock.patch.dict(os.environ, env):
                code = host.wrap(["--agent", agent, "--token", token, "--discovery", discovery, "--", sys.executable, str(script), *agent_args],
                                 stdin=io.BytesIO(b"Do it."), stdout=stream)
        finally:
            os.chdir(previous)
        return code, stream.getvalue()

    def exposure(self, agent, stream):
        """The harness's run dir for the one run, the slot moved beside it, and
        what screen.py reads from both."""
        run_base = self.work / "runs" / "case" / "with_skill"
        run_base.mkdir(parents=True)
        (self.work / "tasks.jsonl").write_text(json.dumps({"run_dir": "case/with_skill"}) + "\n")
        (run_base / "trace.jsonl").write_bytes(stream)
        (run_base / "events.json").write_text(json.dumps({"events": []}))
        screen.file_harvest(self.work)
        return screen.exposure({"run_base": str(run_base)}, ["poteto-mode/SKILL.md"], agent)

    def test_a_later_slot_is_recovered_even_when_an_earlier_slot_is_refused(self):
        session = str(uuid.uuid4())
        harvest = self.work / "harvest"
        (harvest / "0001").mkdir(parents=True)
        (harvest / "0001" / "workspace.json").write_text(json.dumps({"tree": "wrong"}))
        (harvest / "0002").mkdir()
        (harvest / "0002" / "workspace.json").write_text(json.dumps({"tree": "built"}))
        (harvest / "0002" / "session.json").write_text(json.dumps({"agent": "claude", "session": session}))
        (self.claude_home / "projects" / "-ws" / f"{session}.jsonl").write_text("{}\n")
        rows = [json.dumps({"run_dir": f"case/run-{n}"}) for n in (1, 2)]
        (self.work / "tasks.jsonl").write_text("\n".join(rows) + "\n")

        with self.assertRaisesRegex(screen.ScreenError, "workspace tree wrong is not the built built"):
            screen.file_harvest(self.work, expected_tree="built")

        self.assertFalse((self.claude_home / "projects" / "-ws" / f"{session}.jsonl").exists())
        self.assertTrue(json.loads((harvest / "0002" / "session.json").read_text())["transcripts"])

    def test_claude_run_keeps_its_own_transcript_and_reads_injected(self):
        code, stream = self.wrap("claude", FAKE_CLAUDE, "-p", "--no-session-persistence", "--model", "sonnet")

        record = json.loads((self.work / "harvest" / "0001" / "session.json").read_text())
        session = record["session"]
        result = json.loads(stream.splitlines()[-1])
        self.assertEqual((code, str(uuid.UUID(session))), (0, session))
        self.assertEqual(result["argv"], ["-p", "--model", "sonnet", "--session-id", session])
        self.assertEqual(result["prompt"], "/poteto-mode Do it.")
        self.assertEqual((self.ws / ".claude" / "skills").resolve(), self.ws / "skills" / "pstack")
        self.assertEqual(record, {"agent": "claude", "session": session,
                                  "transcripts": [f"transcripts/claude/-ws/{session}", f"transcripts/claude/-ws/{session}.jsonl"]})
        self.assertEqual(sorted(path.name for path in (self.claude_home / "projects" / "-ws").iterdir()), ["memory", "other.jsonl"])
        self.assertEqual(self.exposure("claude", stream), {"read": [], "entry": "injected"})
        harvested = self.work / "harvest" / "case" / "with_skill" / "transcripts" / "claude" / "-ws"
        self.assertEqual(json.loads((harvested / f"{session}.jsonl").read_text().splitlines()[0]), EXPANSION)
        self.assertTrue((harvested / session / "subagents" / "agent-a1.jsonl").is_file())

    def test_claude_run_leaves_no_project_dir_that_held_only_its_session(self):
        code, stream = self.wrap("claude", FAKE_CLAUDE, "-p", FAKE_PROJECT="-only-this-run")

        session = json.loads((self.work / "harvest" / "0001" / "session.json").read_text())["session"]
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path.name for path in (self.claude_home / "projects").iterdir()), ["-ws"])
        self.assertTrue((self.work / "harvest" / "0001" / "transcripts" / "claude" / "-only-this-run" / f"{session}.jsonl").is_file())

    def test_claude_run_keeps_a_project_dir_that_existed_before_it(self):
        (self.claude_home / "projects" / "-older" / "memory").mkdir(parents=True)

        code, stream = self.wrap("claude", FAKE_CLAUDE, "-p", FAKE_PROJECT="-older")

        session = json.loads((self.work / "harvest" / "0001" / "session.json").read_text())["session"]
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path.name for path in (self.claude_home / "projects" / "-older").iterdir()), ["memory"])
        self.assertTrue((self.work / "harvest" / "0001" / "transcripts" / "claude" / "-older" / f"{session}.jsonl").is_file())

    def test_a_wrapper_the_harness_kills_still_loses_its_transcript_to_the_slot(self):
        token, discovery = screen.ENTRY_INVOCATION["claude"]
        script = self.base / "claude.py"
        script.write_text(SLEEPING_CLAUDE)
        command = [sys.executable, str(ROOT / "host.py"), "wrap", "--agent", "claude", "--token", token, "--discovery", discovery,
                   "--", sys.executable, str(script), "-p"]
        with subprocess.Popen(command, cwd=self.ws, stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True) as process:
            process.stdin.write(b"Do it.")
            process.stdin.close()
            init = process.stdout.readline()
            os.killpg(process.pid, signal.SIGKILL)
        session = json.loads(init)["session_id"]
        self.assertTrue((self.claude_home / "projects" / "-ws" / f"{session}.jsonl").is_file())

        self.assertEqual(self.exposure("claude", init), {"read": [], "entry": "injected"})

        run = self.work / "harvest" / "case" / "with_skill"
        self.assertEqual(json.loads((run / "session.json").read_text()), {"agent": "claude", "session": session,
                         "transcripts": [f"transcripts/claude/-ws/{session}", f"transcripts/claude/-ws/{session}.jsonl"]})
        self.assertEqual(json.loads((run / "transcripts" / "claude" / "-ws" / f"{session}.jsonl").read_text().splitlines()[0]), EXPANSION)
        self.assertTrue((run / "transcripts" / "claude" / "-ws" / session / "subagents" / "agent-a1.jsonl").is_file())
        self.assertEqual(sorted(path.name for path in (self.claude_home / "projects" / "-ws").iterdir()), ["memory", "other.jsonl"])

    def test_claude_run_whose_init_lacks_the_entry_is_not_registered(self):
        code, stream = self.wrap("claude", FAKE_CLAUDE, "-p", "--no-session-persistence", FAKE_SKILLS="how")

        self.assertEqual((code, self.exposure("claude", stream)["entry"]), (0, "not registered"))

    def test_codex_run_keeps_its_own_rollout_and_its_delegates_and_reads_injected(self):
        code, stream = self.wrap("codex", FAKE_CODEX, "exec", "--json", "--ephemeral", "--ignore-user-config", "-")

        record = json.loads((self.work / "harvest" / "0001" / "session.json").read_text())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.splitlines()[-1])["argv"], ["exec", "--json", "--ignore-user-config", "-"])
        self.assertEqual(json.loads(stream.splitlines()[1])["item"]["text"], "$poteto-mode Do it.")
        self.assertEqual(record, {"agent": "codex", "session": "0f0f0f0f-aaaa-bbbb-cccc-000000000001", "transcripts": [
            "transcripts/codex/sessions/2026/09/30/rollout-2026-09-30T00-00-00-0f0f0f0f-aaaa-bbbb-cccc-000000000001.jsonl",
            "transcripts/codex/sessions/2026/09/30/rollout-2026-09-30T00-00-01-0f0f0f0f-aaaa-bbbb-cccc-000000000002.jsonl"]})
        self.assertEqual([path.name for path in (self.codex_home / "sessions").rglob("rollout-*.jsonl")], ["rollout-2026-09-29T00-00-00-other.jsonl"])
        self.assertEqual(self.exposure("codex", stream), {"read": [], "entry": "injected"})

    def test_codex_run_that_announces_no_thread_moves_nothing(self):
        code, stream = self.wrap("codex", SILENT, "exec", "--json", "-")

        self.assertEqual((code, stream), (0, b""))
        self.assertEqual(json.loads((self.work / "harvest" / "0001" / "session.json").read_text()), {"agent": "codex", "session": None, "transcripts": []})
        self.assertEqual(self.exposure("codex", stream)["entry"], "not observed")


if __name__ == "__main__":
    unittest.main()
