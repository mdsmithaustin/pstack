import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from harnesses import hermes
from harnesses.hermes_evidence import HermesEvidence, LegacyReplayBinding

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


def tool_call(call_id, tool_name, **arguments):
    return {"id": call_id, "function": {"name": tool_name, "arguments": json.dumps(arguments)}}


def owned_directory(test, prefix):
    retained = os.environ.get("PSTACK_HERMES_TEST_ARTIFACTS")
    if retained:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=retained)).resolve()
    temporary = tempfile.TemporaryDirectory(prefix=prefix)
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name).resolve()


def bind_legacy(run, cleanup):
    (run.root / "run.json").write_text(json.dumps({"turns": run.turns}))
    for index, turn in enumerate(run.turns):
        (run.root / "transcripts" / f"turn-{index}.stream.jsonl").write_text(json.dumps({"type": "system", "session_id": turn["session_id"]}) + "\n")
        (run.root / "transcripts" / f"turn-{index}.stderr.txt").write_text("")
    retained = os.environ.get("PSTACK_HERMES_TEST_ARTIFACTS")
    private = tempfile.mkdtemp(prefix="hermes-test-private-", dir=retained)
    if not retained:
        import shutil
        cleanup(lambda: shutil.rmtree(private))
    run._hermes_evidence = HermesEvidence.replay_legacy(
        LegacyReplayBinding(run.root, str(run.project), ("w", "p"), "native-profile", "owned fixture writer closed"),
        Path(private).resolve())
    cleanup(run._hermes_evidence.close)


class HermesDelegates(unittest.TestCase):
    def setUp(self):
        self.root = owned_directory(self, "pstack-hermes-test-")
        (self.root / "w" / "p").mkdir(parents=True)
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
        bind_legacy(self.run_, self.addCleanup)
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


class HermesTraceParity(unittest.TestCase):
    def test_literal_bridge_todos_root_turns_and_child_reads(self):
        root = owned_directory(self, "hermes-parity-")
        project = root / "w/p"
        project.mkdir(parents=True)
        (project / "a.py").write_text("owned a")
        (project / "b.py").write_text("owned b")
        (root / "hroot/profiles/probe").mkdir(parents=True)
        (root / "transcripts").mkdir()
        (root / "hermes.json").write_text(json.dumps({"image": "img", "cli_version": "1", "entry": "poteto-mode",
            "preload": {"loaded": ["poteto-mode"], "missing": []}, "preloads": {"poteto-mode": {"loaded": ["poteto-mode"]}},
            "todo_eager": True, "todo_tools": "on"}))
        run = SimpleNamespace(root=root, project=project, case={"entry": "poteto-mode", "turns": ["first", "second"]},
            turns=[{"session_id": "root", "hermes_argv": ["hermes", "chat"], "exit_code": 0, "duration_s": 1},
                   {"session_id": "root", "hermes_argv": ["hermes", "chat", "--resume", "root"], "exit_code": 0, "duration_s": 2}])
        db = HermesDatabase(root / "hroot/profiles/probe/state.db")
        db.session("root")
        db.session("kid", parent="root", started=1, model="child-model", usage=(1, 2, 3, 4))
        db.con.execute("update sessions set cwd=?", (str(project),))
        db.message("root", "user", "first")
        db.message("root", "assistant", "1. pending. inspect\n2. completed. plan")
        db.message("root", "assistant", calls=[tool_call("bridge", "tool_call", name="read_file", arguments={"path": "a.py"})])
        db.message("root", "tool", "{}", call_id="bridge")
        db.message("root", "assistant", calls=[tool_call("todo", "todo_list", todos=[])])
        db.message("root", "tool", json.dumps({"todos": [{"content": "inspect", "status": "completed"}]}), call_id="todo")
        db.message("root", "assistant", calls=[tool_call("spawn", "delegate_task", goal="child goal", context="poteto-agent")])
        db.message("root", "tool", json.dumps({"results": [{"task_index": 0, "api_calls": 1, "tokens": {"input": 6, "output": 3}}]}), call_id="spawn")
        db.message("root", "user", "second")
        db.message("root", "assistant", "finished second turn")
        db.message("kid", "user", "child goal")
        db.message("kid", "assistant", "persona: poteto-agent\nchild reply")
        db.message("kid", "assistant", calls=[tool_call("read", "terminal", command="cat b.py")])
        db.message("kid", "tool", '{"exit_code":0}', call_id="read")
        db.done()
        bind_legacy(run, self.addCleanup)
        trace = hermes.harvest(run)
        self.assertNotIn("x_harvest_error", trace)
        self.assertEqual([(e["seq"], e["turn"], e["kind"], e.get("id")) for e in trace["events"]], [
            (0, 0, "user", None), (1, 0, "text", None), (2, 0, "tool_call", "bridge"), (3, 0, "tool_result", "bridge"),
            (4, 0, "tool_call", "todo"), (5, 0, "tool_result", "todo"), (6, 0, "tool_call", "spawn"),
            (7, 0, "tool_result", "spawn"), (8, 1, "user", None), (9, 1, "text", None)])
        self.assertEqual(trace["files_read"], [str(project / "a.py"), str(project / "b.py")])
        self.assertEqual(trace["worklist"], [
            {"seq": 1, "turn": 0, "carrier": "text", "items": [{"text": "pending. inspect", "state": "pending"}, {"text": "completed. plan", "state": "completed"}]},
            {"seq": 5, "turn": 0, "carrier": "todo_list", "items": [{"text": "inspect", "state": "completed"}]}])
        self.assertEqual(trace["spawns"], [{"seq": 6, "turn": 0, "tool": "delegate_task", "persona": "poteto-agent",
            "model": "child-model", "effort": "high", "prompt_head": "child goal\npoteto-agent",
            "x_child_first_reply": "persona: poteto-agent\nchild reply", "x_persona_line": "poteto-agent", "x_child_session": "kid", "x_child_match": "usage"}])
        self.assertEqual((trace["final_reply"], trace["duration_s"], trace["entry"]), ("finished second turn", 3, "injected"))


if __name__ == "__main__":
    unittest.main()
