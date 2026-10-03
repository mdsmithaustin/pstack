import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harnesses import hermes

SESSION_COLUMNS = ("id text, parent_session_id text, model_config text, started_at real, model text, cwd text, "
                   "api_call_count integer, input_tokens integer, output_tokens integer, cache_read_tokens integer")
MESSAGE_COLUMNS = "id integer primary key, session_id text, role text, content text, tool_calls text, tool_call_id text, tool_name text"


class HermesDatabase:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.execute(f"create table sessions ({SESSION_COLUMNS})")
        self.con.execute(f"create table messages ({MESSAGE_COLUMNS})")

    def session(self, sid, parent=None, started=0.0, model="root-model", usage=(0, 0, 0, 0)):
        calls, fresh, out, cached = usage
        config = json.dumps({"reasoning_config": {"effort": "high"}})
        self.con.execute("insert into sessions values (?,?,?,?,?,?,?,?,?,?)",
                         (sid, parent, config, started, model, "/w", calls, fresh, out, cached))

    def message(self, sid, role, content="", calls=None, call_id=None, tool_name=None):
        self.con.execute("insert into messages (session_id, role, content, tool_calls, tool_call_id, tool_name) values (?,?,?,?,?,?)",
                         (sid, role, content, json.dumps(calls) if calls else None, call_id, tool_name))

    def done(self):
        self.con.commit()
        self.con.close()


def tool_call(call_id, name, **arguments):
    return {"id": call_id, "function": {"name": name, "arguments": json.dumps(arguments)}}


class HermesDelegates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-hermes-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "hroot/profiles/probe").mkdir(parents=True)
        (self.root / "transcripts").mkdir()
        (self.root / "hermes.json").write_text(json.dumps({
            "image": "img", "cli_version": "1", "entry": None, "preload": {}, "todo_eager": True, "todo_tools": "on"}))
        self.run_ = SimpleNamespace(root=self.root, project=self.root / "w" / "p", case={"turns": ["go"]},
                                    turns=[{"session_id": "root", "exit_code": 0, "duration_s": 1}])
        self.db = HermesDatabase(self.root / "hroot/profiles/probe/state.db")

    def delegate(self, goals, results):
        tasks = [{"goal": g, "context": f"brief for {g}"} for g in goals]
        self.db.session("root", started=1.0)
        self.db.message("root", "user", "go")
        self.db.message("root", "assistant", calls=[tool_call("c1", "delegate_task", tasks=tasks)])
        self.db.message("root", "tool", json.dumps({"results": results}), call_id="c1", tool_name="delegate_task")
        self.db.message("root", "assistant", "done")

    def child(self, sid, started, goal, model, usage):
        self.db.session(sid, parent="root", started=started, model=model, usage=usage)
        self.db.message(sid, "user", goal)
        self.db.message(sid, "assistant", f"reply from {sid}")

    def harvest(self):
        self.db.done()
        return hermes.harvest(self.run_)

    def test_children_started_out_of_task_order_still_match_their_own_task(self):
        self.delegate(["goal a", "goal b", "goal c"], [
            {"task_index": 0, "api_calls": 3, "tokens": {"input": 1100, "output": 10}, "model": "model-a"},
            {"task_index": 1, "api_calls": 5, "tokens": {"input": 2200, "output": 20}, "model": "model-b"},
            {"task_index": 2, "api_calls": 7, "tokens": {"input": 3300, "output": 30}, "model": "model-c"}])
        self.child("kid-b", 10.0, "goal b", "model-b", (5, 2000, 20, 200))
        self.child("kid-c", 11.0, "goal c", "model-c", (7, 3000, 30, 300))
        self.child("kid-a", 12.0, "goal a", "model-a", (3, 1000, 10, 100))
        spawns = self.harvest()["spawns"]
        self.assertEqual([(s["prompt_head"].splitlines()[0], s["model"], s["x_child_first_reply"]) for s in spawns],
                         [("goal a", "model-a", "reply from kid-a"), ("goal b", "model-b", "reply from kid-b"),
                          ("goal c", "model-c", "reply from kid-c")])
        self.assertEqual([s["x_child_match"] for s in spawns], ["usage"] * 3)

    def test_a_task_with_no_usage_row_falls_back_to_its_goal_then_to_order(self):
        self.delegate(["goal a", "goal b"], [{"task_index": 0}, {"task_index": 1}])
        self.child("kid-b", 10.0, "goal b", "model-b", (1, 1, 1, 1))
        self.child("kid-a", 11.0, "goal a", "model-a", (1, 1, 1, 1))
        spawns = self.harvest()["spawns"]
        self.assertEqual([(s["model"], s["x_child_match"]) for s in spawns], [("model-a", "goal"), ("model-b", "goal")])

    def test_a_failed_delegation_claims_no_child(self):
        self.delegate(["goal a"], [])
        self.db.message("root", "tool", json.dumps({"error": "budget exhausted"}), call_id="c1", tool_name="delegate_task")
        self.assertEqual(self.harvest()["spawns"][0]["model"], None)

    def test_tool_events_carry_the_call_id(self):
        self.db.session("root", started=1.0)
        self.db.message("root", "user", "go")
        self.db.message("root", "assistant", calls=[tool_call("c1", "terminal", command="a"), tool_call("c2", "terminal", command="b")])
        self.db.message("root", "tool", json.dumps({"exit_code": 1}), call_id="c2", tool_name="terminal")
        self.db.message("root", "tool", json.dumps({"exit_code": 0}), call_id="c1", tool_name="terminal")
        events = [(e["kind"], e.get("id"), e.get("ok")) for e in self.harvest()["events"] if e["kind"].startswith("tool")]
        self.assertEqual(events, [("tool_call", "c1", None), ("tool_call", "c2", None), ("tool_result", "c2", False), ("tool_result", "c1", True)])


class HermesContainerStatus(unittest.TestCase):
    def setUp(self):
        self.run_ = SimpleNamespace(root=Path("/r"), project=Path("/r/w/p"))
        patcher = mock.patch.object(hermes, "hermes_image", return_value="img")
        patcher.start()
        self.addCleanup(patcher.stop)

    def docker(self, code, out="", err=""):
        return mock.patch.object(hermes.subprocess, "run", return_value=subprocess.CompletedProcess([], code, out, err))

    def test_a_failed_docker_run_raises_with_its_stderr(self):
        with self.docker(125, "", "Unable to find image 'img'"):
            with self.assertRaisesRegex(RuntimeError, "Unable to find image"):
                hermes.run_in_container(self.run_, "version", hermes.HERMES_BIN, ["--version"])

    def test_a_successful_probe_returns_stripped_stdout(self):
        with self.docker(0, " Hermes 1.2\n"):
            self.assertEqual(hermes.run_in_container(self.run_, "version", hermes.HERMES_BIN, ["--version"]), "Hermes 1.2")


if __name__ == "__main__":
    unittest.main()
