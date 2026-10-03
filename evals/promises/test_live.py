import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import live

CODEX_CHAT = """I'm using `poteto-mode`. I'll identify the command first.

1. In progress. **You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.
2. Pending. `how` over the affected subsystem.
3. ⏭️ `architect`. skipped: one module
4. [x] Verify on the matching surface."""


class ChatWorklist(unittest.TestCase):
    def test_capitalized_states_skips_and_checkboxes_parse(self):
        items = live.chat_worklist(CODEX_CHAT)
        self.assertEqual([i["state"] for i in items], ["in progress", "pending", "skipped: one module", "completed"])
        self.assertEqual(items[1]["text"], "Pending. `how` over the affected subsystem.")

    def test_a_list_with_no_state_is_not_a_worklist(self):
        self.assertIsNone(live.chat_worklist("1. read the code\n2. write the fix"))

    def test_a_reply_summary_with_one_state_word_is_not_a_worklist(self):
        reply = "Summary\n- the flag now emits rows\n- default text stays byte-identical\n- verification done for both forms"
        self.assertIsNone(live.chat_worklist(reply))

    def test_bare_checkbox_lines_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("[x] one\n[ ] two\n- [~] three")],
                         ["completed", "pending", "in progress"])


class FixtureCommits(unittest.TestCase):
    def test_commits_ignore_the_contributors_signing_and_hook_settings(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            tmp = Path(tmp)
            hooks = tmp / "hooks"
            hooks.mkdir()
            (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
            (hooks / "pre-commit").chmod(0o755)
            config = tmp / "gitconfig"
            config.write_text(f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /usr/bin/false\n[core]\n\thooksPath = {hooks}\n"
                              "[user]\n\tname = Someone Else\n\temail = someone@example.org\n")
            case = {"fixture": "relay", "history": "relay-retry-limit"}
            dest = tmp / "project"
            with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
                live.make_project(case, dest)
            log = subprocess.run(["git", "-C", str(dest), "log", "--format=%an <%ae>"], capture_output=True, text=True,
                                 env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}).stdout.split("\n")
            self.assertEqual({line for line in log if line}, {"dev <dev@example.com>"})
            self.assertGreater(len([line for line in log if line]), 1)


class GradeRun(unittest.TestCase):
    def test_a_run_with_host_skill_hits_writes_inconclusive_for_every_promise(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            root = Path(tmp)
            case = live.load_case("feature-run")
            trace = {"harness": "claude-code", "model": "m", "exit_code": 0, "events": [], "worklist": [], "spawns": [],
                     "files_read": [], "final_reply": "done", "x_host_skill_hits": ["/Users/someone/.claude/skills"]}
            (root / "run.json").write_text(json.dumps({"harness": "claude-code", "case": case["id"], "skills_at": "x", "project": str(root / "p")}))
            (root / "trace.json").write_text(json.dumps(trace))
            graded = live.grade(root)
            self.assertEqual({r["verdict"] for r in graded["promises"].values()}, {"INCONCLUSIVE"})
            self.assertEqual(set(graded["promises"]), set(case["promises"]))
            self.assertEqual(json.loads((root / "verdict.json").read_text()), graded)

    def test_a_run_with_a_clean_turn_is_graded_even_when_the_trace_carries_only_the_last_exit_code(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            root = Path(tmp)
            case = live.load_case("principle-steer-run")
            trace = {"harness": "claude-code", "model": "m", "exit_code": 1, "events": [{"seq": 0, "kind": "text", "text": "Done."}],
                     "worklist": [], "spawns": [], "files_read": [], "final_reply": "Done."}
            run = {"harness": "claude-code", "case": case["id"], "skills_at": "x", "project": str(root / "p"),
                   "turns": [{"exit_code": 0}, {"exit_code": 1}]}
            (root / "run.json").write_text(json.dumps(run))
            (root / "trace.json").write_text(json.dumps(trace))
            graded = live.grade(root)
            self.assertNotIn("never started", json.dumps(graded))



class MakeProject(unittest.TestCase):
    def build(self, commit, branch=None, extra_steps=()):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        (tmp / "fixtures" / "app").mkdir(parents=True)
        (tmp / "fixtures" / "app" / "a.py").write_text('x = "1"\n')
        step = tmp / "histories" / "h" / "step-1"
        step.mkdir(parents=True)
        (step / "a.py").write_text("x = '1'\n")
        for path in (tmp / "fixtures" / "app" / "a.py", step / "a.py"):
            os.utime(path, (1_700_000_000, 1_700_000_000))
        steps = [{"dir": "step-1", "message": "quote style", "commit": commit, **({"branch": branch} if branch else {})}]
        for n, extra in enumerate(extra_steps, start=2):
            (tmp / "histories" / "h" / f"step-{n}").mkdir()
            (tmp / "histories" / "h" / f"step-{n}" / f"f{n}.py").write_text(f"y = {n}\n")
            steps.append({"dir": f"step-{n}", "message": f"step {n}", **extra})
        (tmp / "histories" / "h" / "steps.json").write_text(json.dumps({"fixture": "app", "steps": steps}))
        old = (live.FIXTURES, live.HISTORIES)
        live.FIXTURES, live.HISTORIES = tmp / "fixtures", tmp / "histories"
        self.addCleanup(lambda: setattr(live, "FIXTURES", old[0]) or setattr(live, "HISTORIES", old[1]))
        project = tmp / "work" / "app"
        live.make_project({"fixture": "app", "history": "h"}, project)
        git = lambda *a: subprocess.run(["git", "-C", str(project), *a], capture_output=True, text=True).stdout
        return git

    def test_a_same_size_edit_in_a_history_step_is_committed(self):
        git = self.build(True)
        self.assertEqual(git("log", "--format=%s"), "quote style\ninitial import\n")
        self.assertEqual(git("show", "HEAD:a.py"), "x = '1'\n")

    def test_an_uncommitted_step_stays_in_the_working_tree(self):
        git = self.build(False)
        self.assertEqual(git("log", "--format=%s"), "initial import\n")
        self.assertEqual(git("status", "--short"), " M a.py\n")

    def test_a_step_with_a_branch_commits_there_and_leaves_main_alone(self):
        git = self.build(True, branch="team-filter")
        self.assertEqual(git("branch", "--show-current"), "team-filter\n")
        self.assertEqual(git("log", "--format=%s", "main"), "initial import\n")
        self.assertEqual(git("diff", "--name-only", "main...HEAD"), "a.py\n")

    def test_a_later_step_on_an_existing_branch_keeps_its_commits(self):
        git = self.build(True, branch="feature", extra_steps=[{"branch": "main"}])
        self.assertEqual(git("log", "--format=%s", "main"), "step 2\ninitial import\n")
        self.assertEqual(git("log", "--format=%s", "feature"), "quote style\ninitial import\n")

    def test_the_baseline_holds_every_branchs_commits_and_ends_at_head(self):
        git = self.build(True, branch="feature", extra_steps=[{"branch": "main"}])
        project = Path(git("rev-parse", "--show-toplevel").strip())
        base = live.baseline(project)
        self.assertEqual(sorted(base), sorted(git("rev-list", "--branches").split()))
        self.assertEqual(base[-1], git("rev-parse", "HEAD").strip())
        self.assertEqual(base[0], git("rev-list", "--max-parents=0", "HEAD").strip())


if __name__ == "__main__":
    unittest.main()
