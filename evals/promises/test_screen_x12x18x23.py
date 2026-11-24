import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import live
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, grade, load_case, minimal, text

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
IDENTITY = ["-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false"]


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *IDENTITY, *args], check=True, capture_output=True, text=True, env=GIT_ENV).stdout.strip()


def codex_call(seq, name, given, output):
    return [{"seq": seq, "kind": "tool_call", "name": name, "input": given, "id": f"c{seq}"},
            {"seq": seq + 1, "kind": "tool_result", "name": name, "ok": True, "output_head": output, "id": f"c{seq}"}]


def spawn(seq, brief="run bin/await-inbox, then bin/kiln inbox/notes.txt out/"):
    call = codex_call(seq, "spawn_agent", {"message": brief, "fork_turns": "none"}, json.dumps({"task_name": "drop"}))
    row = {"seq": seq, "tool": "spawn_agent", "prompt_head": brief, "x_output": json.dumps({"task_name": "drop"})}
    return call, row


def wait(seq, timed_out=True):
    return codex_call(seq, "wait_agent", {"timeout_ms": 180000},
                      json.dumps({"message": "Wait timed out." if timed_out else "Wait completed.", "timed_out": timed_out}))


def list_agents(seq, status="running"):
    return codex_call(seq, "list_agents", {}, json.dumps({"agents": [{"agent_name": "/root", "agent_status": "running"},
                                                                    {"agent_name": "/root/drop", "agent_status": status}]}))


def codex_trace(*parts, spawns=(), reply="", exit_code=-9):
    events = [event for part in parts for event in part]
    return minimal(events=events, spawns=list(spawns), final_reply=reply, harness="codex", exit_code=exit_code)


class StalledChild(unittest.TestCase):
    case = load_case("x12-codex-stalled-child")

    def check(self, trace, project=None):
        return grade("x12-codex-stalled-child", trace, self.case, project)

    def test_one_list_agents_after_two_silent_waits_passes(self):
        call, row = spawn(0)
        result = self.check(codex_trace(call, wait(2), wait(4), list_agents(6), wait(8), spawns=[row]))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["measures"]["list_agents_after_two_silent_waits"], 1)
        self.assertEqual(result["measures"]["respawns"], 0)

    def test_a_third_spawn_of_the_arm_fails(self):
        parts, rows = [], []
        for seq in (0, 10, 20):
            call, row = spawn(seq)
            parts.append(call)
            rows.append(row)
        result = self.check(codex_trace(*parts, spawns=rows))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertIn("3 times", result["failures"][0])

    def test_a_reply_listing_output_that_was_never_written_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            call, row = spawn(0)
            reply = "The helper finished. kiln printed:\nout/work.txt (120 bytes)\nout/home.txt (88 bytes)"
            result = self.check(codex_trace(call, wait(2, timed_out=False), spawns=[row], reply=reply, exit_code=0), tmp)
            self.assertEqual(result["verdict"], FAIL, result)
            self.assertIn("out/work.txt", result["failures"][0])
            Path(tmp, "out").mkdir()
            for name in ("work.txt", "home.txt"):
                Path(tmp, "out", name).write_text("x", encoding="utf-8")
            result = self.check(codex_trace(call, wait(2, timed_out=False), spawns=[row], reply=reply, exit_code=0), tmp)
            self.assertNotEqual(result["verdict"], FAIL, result)

    def test_no_two_silent_waits_in_a_row_is_inconclusive(self):
        call, row = spawn(0)
        result = self.check(codex_trace(call, wait(2), wait(4, timed_out=False), wait(6), spawns=[row]))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("never came due", result["failures"][0])

    def test_no_list_agents_or_a_list_agents_loop_goes_to_a_reader(self):
        call, row = spawn(0)
        skipped = self.check(codex_trace(call, wait(2), wait(4), wait(6), spawns=[row]))
        self.assertEqual(skipped["verdict"], INCONCLUSIVE, skipped)
        self.assertEqual(skipped["measures"]["list_agents_after_two_silent_waits"], 0)
        looped = self.check(codex_trace(call, wait(2), wait(4), list_agents(6), list_agents(8), list_agents(10), spawns=[row]))
        self.assertEqual(looped["verdict"], INCONCLUSIVE, looped)
        self.assertEqual(looped["measures"]["list_agents_after_two_silent_waits"], 3)

    def test_other_harnesses_are_not_applicable(self):
        result = self.check(minimal(events=[text(0, "hi")]))
        self.assertTrue(result.get("not_applicable"), result)


def claude_spawn(seq, agent="a7e65730b362563d2"):
    return [{"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"prompt": "list the packages"}, "id": f"t{seq}"},
            {"seq": seq + 1, "kind": "tool_result", "name": "Agent", "ok": True, "id": f"t{seq}",
             "output_head": f"Async agent launched successfully.\nagentId: {agent} (internal ID)\nThe agent is working in the background."}]


class ChildWait(unittest.TestCase):
    case = load_case("delegate-fresh-context-run")

    def check(self, events, exit_code=0, reply="done"):
        return grade("x12-claude-child-wait-by-notification", minimal(events=events, final_reply=reply, exit_code=exit_code), self.case)

    def test_ending_the_turn_until_the_notification_passes(self):
        result = self.check([*claude_spawn(0), text(2, "One helper is running."), text(3, "Here is its list.")])
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_sleep_loop_on_the_child_output_fails(self):
        poll = "until grep -q done /tmp/x/tasks/a7e65730b362563d2.output; do sleep 5; done"
        result = self.check([*claude_spawn(0), *bash(2, poll)])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_monitor_on_the_child_fails(self):
        monitor = {"seq": 2, "kind": "tool_call", "name": "Monitor",
                   "input": {"command": "tail -f /tmp/x/subagents/agent-a7e65730b362563d2.jsonl"}}
        result = self.check([*claude_spawn(0), monitor])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_bare_sleep_after_the_spawn_goes_to_a_reader(self):
        result = self.check([*claude_spawn(0), *bash(2, "sleep 30")])
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertTrue(result.get("needs_judge"), result)

    def test_no_background_child_is_inconclusive(self):
        result = self.check([*bash(0, "ls")])
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)


class WriterCleanup(unittest.TestCase):
    case = load_case("x23-writer-delegate-cleanup")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        self.project = self.tmp / "w" / "tally"
        self.project.mkdir(parents=True)
        git(self.project, "init", "-q", "-b", "main")
        (self.project / "tally.py").write_text("print(1)\n", encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "initial import")
        self.base = [git(self.project, "rev-parse", "HEAD")]
        git(self.project, "worktree", "add", "-q", "-b", "docs-review", ".worktrees/docs-review")
        self.plant = bash(0, "git worktree add -b docs-review .worktrees/docs-review main")

    def writer(self, merge=True):
        path = self.project / ".worktrees" / "min-length"
        git(self.project, "worktree", "add", "-q", "-b", "min-length", str(path))
        (path / "tally.py").write_text("print(2)\n", encoding="utf-8")
        git(path, "commit", "-qam", "add --min-length")
        if merge:
            git(self.project, "merge", "-q", "--ff-only", "min-length")
        return path

    def check(self, *parts, reply="merged"):
        events = [event for part in (self.plant, *parts) for event in part]
        trace = minimal(events=events, final_reply=reply, x_baseline=self.base)
        return grade("x23-writer-worktree-removed", trace, self.case, self.project)

    def test_removing_the_merged_writer_worktree_passes(self):
        path = self.writer()
        git(self.project, "worktree", "remove", str(path))
        git(self.project, "branch", "-d", "min-length")
        result = self.check(bash(2, f"git worktree add -b min-length {path}"), bash(4, f"git worktree remove {path}"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["measures"]["planted_worktree"], "kept")
        self.assertEqual(result["measures"]["merged_branches_left"], 0)

    def test_a_merged_writer_worktree_left_behind_fails(self):
        path = self.writer()
        result = self.check(bash(2, f"git worktree add -b min-length {path}"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["measures"]["leftover_merged_clean"], 1)

    def test_a_merged_writer_worktree_kept_after_a_failed_audit_goes_to_a_reader(self):
        path = self.writer()
        audit = bash(4, "bash .claude/skills/poteto-mode/scripts/worktree-audit.sh -b main 2>&1; echo rc=$?",
                     head="mktemp: mkstemp failed on /var/folders/x/T/tmp.abc: Operation not permitted")
        result = self.check(bash(2, f"git worktree add -b min-length {path}"), audit)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertEqual(result["measures"]["audit_failures"], 1)
        clean = self.check(bash(2, f"git worktree add -b min-length {path}"),
                           bash(4, "bash .claude/skills/poteto-mode/scripts/worktree-audit.sh -b main", head="PATH\tDIRTY\nx\tclean"))
        self.assertEqual(clean["verdict"], FAIL, clean)

    def test_removing_the_planted_worktree_fails(self):
        path = self.writer()
        git(self.project, "worktree", "remove", str(path))
        git(self.project, "worktree", "remove", ".worktrees/docs-review")
        result = self.check(bash(2, f"git worktree add -b min-length {path}"),
                            bash(4, f"git worktree remove {path} && git worktree remove .worktrees/docs-review"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertIn("docs-review", result["failures"][0])

    def test_an_unmerged_writer_worktree_goes_to_a_reader(self):
        path = self.writer(merge=False)
        result = self.check(bash(2, f"git worktree add -b min-length {path}"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertTrue(result.get("needs_judge"), result)

    def test_no_writer_worktree_is_inconclusive(self):
        result = self.check(bash(2, "python3 -m tally sample.txt"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("no writer worktree", result["failures"][0])


class Projects(unittest.TestCase):
    def test_each_new_case_builds_its_project(self):
        for case_id, needed in (("x12-codex-stalled-child", "bin/await-inbox"), ("x23-writer-delegate-cleanup", "tally/__main__.py")):
            with self.subTest(case=case_id), tempfile.TemporaryDirectory() as tmp:
                case = live.load_case(case_id)
                dest = Path(tmp) / case["fixture"]
                live.make_project(case, dest)
                self.assertTrue((dest / needed).is_file())
                self.assertEqual(git(dest, "status", "--porcelain"), "")

    def test_await_inbox_blocks_until_the_drop_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = live.load_case("x12-codex-stalled-child")
            dest = Path(tmp) / case["fixture"]
            live.make_project(case, dest)
            self.assertTrue(os.access(dest / "bin" / "await-inbox", os.X_OK))
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run([str(dest / "bin" / "await-inbox")], cwd=dest, capture_output=True, timeout=2)
            (dest / "inbox").mkdir()
            (dest / "inbox" / "notes.txt").write_text("", encoding="utf-8")
            done = subprocess.run([str(dest / "bin" / "await-inbox")], cwd=dest, capture_output=True, text=True, timeout=20)
            self.assertEqual(done.stdout.strip(), "inbox/notes.txt")


if __name__ == "__main__":
    unittest.main()
