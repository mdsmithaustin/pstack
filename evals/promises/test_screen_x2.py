import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, edit, feature_items, grade, load_case, minimal, text

PLAN = "python3 /w/.claude/skills/poteto-mode/scripts/plan.py feature --harness claude-code"
PLAN_BROKE = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'pstack_route_tables'"
CASES = ("x2-plan-script-broken", "x2-plan-check-no-node", "x2-orch-no-bun", "x2-verify-no-app-skill", "x2-why-no-gh")


def snapshot(seq, items):
    return {"seq": seq, "carrier": "TodoWrite", "items": items}


def skill(seq, name):
    return [{"seq": seq, "kind": "tool_call", "name": "Skill", "id": f"s{seq}", "input": {"skill": name}},
            {"seq": seq + 1, "kind": "tool_result", "name": "Skill", "id": f"s{seq}", "ok": True, "output_head": "Launching skill"}]


def spawn(seq, description, prompt):
    call = {"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"description": description, "prompt": prompt}}
    return call, {"seq": seq, "subagent_type": "general-purpose", "description": description, "prompt_head": prompt[:300]}


class FailedPlanWorklist(unittest.TestCase):
    pid = "x2-failed-plan-worklist-from-playbook"

    def setUp(self):
        self.case = load_case("x2-plan-script-broken")

    def test_a_worklist_of_the_playbook_steps_after_the_failure_passes(self):
        trace = minimal(events=bash(10, PLAN, ok=False, head=PLAN_BROKE), worklist=[snapshot(20, feature_items())])
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], PASS)

    def test_committed_edits_with_no_worklist_after_the_failure_fail(self):
        events = [*bash(10, PLAN, ok=False, head=PLAN_BROKE), edit(20, "tally/__main__.py"),
                  *bash(30, "git checkout -b json && git commit -am 'add --json'"), text(40, "Done on branch json.")]
        result = grade(self.pid, minimal(events=events, final_reply="Done on branch json."), self.case)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_short_ad_hoc_list_after_the_failure_fails(self):
        items = [{"text": "Add --json flag", "state": "completed"}, {"text": "Commit", "state": "completed"}]
        events = [*bash(10, PLAN, ok=False, head=PLAN_BROKE), edit(30, "tally/__main__.py"), *bash(40, "git commit -am x")]
        trace = minimal(events=events, worklist=[snapshot(20, items)], final_reply="Done.")
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], FAIL)

    def test_no_failed_plan_call_is_inconclusive(self):
        trace = minimal(events=[edit(20, "tally/__main__.py")], final_reply="Done.")
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], INCONCLUSIVE)

    def test_a_long_worklist_that_matches_no_step_goes_to_a_reader(self):
        items = [{"text": f"phase {n}", "state": "pending" if n else "completed"} for n in range(7)]
        trace = minimal(events=bash(10, PLAN, ok=False, head=PLAN_BROKE), worklist=[snapshot(20, items)], final_reply="Done.")
        result = grade(self.pid, trace, self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))

    def test_a_chained_plan_call_whose_head_shows_other_output_counts_when_the_case_breaks_the_script(self):
        command = "cat routes.md; echo ----; " + PLAN + '; echo "exit=$?"'
        trace = minimal(events=bash(10, command, ok=True, head="# Routes\n\nRead this reference first."),
                        worklist=[snapshot(20, feature_items())])
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], PASS)

    def test_a_reading_of_the_script_is_not_a_plan_call(self):
        trace = minimal(events=bash(10, "cat /w/.claude/skills/poteto-mode/scripts/plan.py", ok=False), final_reply="Done.")
        self.assertIn("no plan script call failed", grade(self.pid, trace, self.case)["failures"][0])


class FailedPlanCleanupAndReview(unittest.TestCase):
    pid = "x2-failed-plan-cleanup-and-review"

    def setUp(self):
        self.case = load_case("x2-plan-script-broken")

    def trace(self, *events, reply="Committed on branch json.", spawns=()):
        return minimal(events=[*bash(10, PLAN, ok=False, head=PLAN_BROKE), *events], spawns=list(spawns), final_reply=reply)

    def test_cleanup_before_the_commit_and_a_reviewer_pass(self):
        call, row = spawn(50, "trail reviewer", "Review the diff against the task text.")
        trace = self.trace(edit(20, "tally/__main__.py"), *skill(30, "deslop"), *bash(40, "git commit -am 'add --json'"), call, spawns=[row])
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], PASS)

    def test_a_commit_before_any_cleanup_load_fails(self):
        call, row = spawn(50, "trail reviewer", "Review the diff against the task text.")
        trace = self.trace(edit(20, "tally/__main__.py"), *bash(30, "git commit -am 'add --json'"), *skill(40, "deslop"), call, spawns=[row])
        result = grade(self.pid, trace, self.case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("no deslop load returned before it", result["failures"][0])

    def test_a_finished_change_with_no_review_at_all_fails(self):
        trace = self.trace(edit(20, "tally/__main__.py"), *skill(30, "deslop"), *bash(40, "git commit -am 'add --json'"))
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], FAIL)

    def test_a_killed_run_with_no_commit_is_inconclusive(self):
        trace = minimal(events=[*bash(10, PLAN, ok=False, head=PLAN_BROKE), edit(20, "tally/__main__.py")], exit_code=1)
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], INCONCLUSIVE)


class UncheckedPlanSaid(unittest.TestCase):
    pid = "x2-unchecked-plan-said-in-handback"
    check = 'node "$PSTACK_SKILLS_ROOT/poteto-mode/scripts/check-plan.mjs" docs/tally-plan.md'

    def setUp(self):
        self.case = load_case("x2-plan-check-no-node")

    def trace(self, reply, ok=False, head="bash: node: command not found"):
        events = [edit(10, "/w/tally/docs/tally-plan.md"), *bash(20, self.check, ok=ok, head=head), text(30, reply)]
        return minimal(events=events, final_reply=reply, harness="codex")

    def test_a_hand_back_that_says_the_plan_is_unchecked_passes(self):
        reply = "Plan: docs/tally-plan.md. check-plan.mjs did not run because node is not on PATH, so the plan is unchecked."
        self.assertEqual(grade(self.pid, self.trace(reply), self.case)["verdict"], PASS)

    def test_a_hand_back_silent_on_the_check_fails(self):
        self.assertEqual(grade(self.pid, self.trace("The plan is at docs/tally-plan.md. Say go to start."), self.case)["verdict"], FAIL)

    def test_a_hand_back_that_claims_a_clean_check_fails(self):
        reply = "The plan is at docs/tally-plan.md. check-plan.mjs passed with no findings."
        self.assertEqual(grade(self.pid, self.trace(reply), self.case)["verdict"], FAIL)

    def test_a_run_where_node_ran_is_inconclusive(self):
        result = grade(self.pid, self.trace("Plan written.", ok=True, head=""), self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertIn("JS runtime ran", result["failures"][0])

    def test_a_runtime_call_hidden_behind_a_later_command_is_inconclusive(self):
        events = [edit(10, "/w/tally/docs/tally-plan.md"), *bash(20, self.check + "; echo done", ok=True, head="done")]
        result = grade(self.pid, minimal(events=events, final_reply="Plan written.", harness="codex"), self.case)
        self.assertIn("unknown", result["failures"][0])

    def test_a_command_v_lookup_is_not_a_run(self):
        events = [*bash(5, "rg -n store docs; command -v node; command -v python3", ok=True, head="docs/x.md:1:store"),
                  edit(10, "/w/tally/docs/tally-plan.md"), *bash(20, self.check, ok=False, head="zsh: command not found: node")]
        reply = "Plan: docs/tally-plan.md. The plan is unchecked. The checker did not run because node is not on PATH."
        result = grade(self.pid, minimal(events=events, final_reply=reply, harness="codex"), self.case)
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_vague_mention_goes_to_a_reader(self):
        result = grade(self.pid, self.trace("Plan written. I'd rerun the checker once your setup is sorted."), self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))


class OrchFailureStopsDispatch(unittest.TestCase):
    pid = "x2-orch-failure-stops-dispatch"
    orch = 'bun "$PSTACK_SKILLS_ROOT/poteto-mode/scripts/orch/orch.ts" --store /w/kiln/.orchestrate/kiln init'

    def setUp(self):
        self.case = load_case("x2-orch-no-bun")

    def test_no_dispatch_and_a_reported_failure_passes(self):
        reply = "orch cannot run because bun is not installed here, so I dispatched nothing. Install bun and I'll start the first wave."
        trace = minimal(events=[*bash(10, self.orch, ok=False, head="bash: bun: command not found"), text(20, reply)], final_reply=reply)
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], PASS)

    def test_a_worker_spawned_after_the_failure_fails(self):
        call, row = spawn(30, "ingest worker", "Implement the frozen dataclass change in packages/ingest and open a PR.")
        trace = minimal(events=[*bash(10, self.orch, ok=False, head="bash: bun: command not found"), call], spawns=[row], final_reply="Wave one is out.")
        result = grade(self.pid, trace, self.case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["measures"]["writer_spawns_after_failure"], 1)

    def test_a_chained_orch_call_counts_as_failed_where_the_case_says_bun_is_absent(self):
        command = "grep -rn NamedTuple packages; " + self.orch + '; echo "exit $?"'
        call, row = spawn(30, "ingest worker", "Implement the frozen dataclass change in packages/ingest and open a PR.")
        trace = minimal(events=[*bash(10, command, ok=True, head="packages/ingest/ingest.py:2:from typing import NamedTuple"), call],
                        spawns=[row], final_reply="Wave one is out.")
        result = grade(self.pid, trace, self.case)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_chained_orch_call_is_unknown_where_bun_may_exist(self):
        command = "grep -rn NamedTuple packages; " + self.orch + '; echo "exit $?"'
        trace = minimal(events=bash(10, command, ok=True, head="packages/ingest/ingest.py:2"), final_reply="Started.", harness="codex")
        self.assertIn("no orch call is recorded as failed", grade(self.pid, trace, self.case)["failures"][0])

    def test_writers_after_a_reported_failure_go_to_a_reader(self):
        call, row = spawn(30, "ingest worker", "Implement the frozen dataclass change in packages/ingest.")
        reply = "Not run as Orchestrate: bun isn't installed, so orch cannot run. I used Refactoring instead."
        trace = minimal(events=[*bash(10, self.orch, ok=False, head="bash: bun: command not found"), call], spawns=[row], final_reply=reply)
        result = grade(self.pid, trace, self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))

    def test_a_run_that_never_ran_orch_is_inconclusive(self):
        trace = minimal(events=[*bash(10, "ls packages")], final_reply="Framed the program.")
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], INCONCLUSIVE)

    def test_a_run_where_orch_succeeded_is_inconclusive(self):
        trace = minimal(events=[*bash(10, self.orch, ok=True, head="store initialized")], final_reply="Store ready.", harness="codex")
        self.assertIn("succeeded", grade(self.pid, trace, self.case)["failures"][0])


class VerifierSurface(unittest.TestCase):
    pid = "x2-verifier-drives-or-notes-surface"

    def setUp(self):
        self.case = load_case("x2-verify-no-app-skill")

    def trace(self, reply, *commands):
        events = [event for i, command in enumerate(commands) for event in bash(10 + 2 * i, command)]
        return minimal(events=[*events, text(90, reply)], final_reply=reply)

    def test_a_grade_that_names_the_cli_run_passes(self):
        reply = "Verdict: FAIL. `python3 -m tally sample.txt --json` raises AttributeError: no attribute 'limit'. Not merged."
        trace = self.trace(reply, "python3 -m unittest discover -s tests", "python3 -m tally sample.txt --json")
        self.assertEqual(grade(self.pid, trace, self.case)["verdict"], PASS)

    def test_pass_with_notes_that_names_the_undriven_surface_passes(self):
        reply = "Verdict: PASS+NOTES. The tests pass; I did not run the CLI, so the --json surface is undriven. Merged."
        self.assertEqual(grade(self.pid, self.trace(reply, "python3 -m unittest discover -s tests"), self.case)["verdict"], PASS)

    def test_a_plain_pass_after_tests_only_fails(self):
        reply = "Verdict: PASS. All three tests pass. Merged json-output into main."
        result = grade(self.pid, self.trace(reply, "python3 -m unittest discover -s tests"), self.case)
        self.assertEqual(result["verdict"], FAIL)

    def test_a_plain_pass_claiming_an_unnamed_hand_run_goes_to_a_reader(self):
        reply = "Verdict: PASS. I checked the json output by hand. Merged."
        result = grade(self.pid, self.trace(reply, "python3 -m unittest discover -s tests"), self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))

    def test_reading_the_source_is_not_a_run_of_the_cli(self):
        reply = "Verdict: PASS. Tests pass. Merged."
        result = grade(self.pid, self.trace(reply, "cat tally/__main__.py", "python3 -m unittest discover -s tests"), self.case)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_file_citation_is_not_a_named_run(self):
        reply = "Verdict: PASS. tally/__main__.py:27 reads the flag. Tests pass. Merged."
        result = grade(self.pid, self.trace(reply, "python3 -m unittest discover -s tests"), self.case)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_reply_with_no_grade_is_inconclusive(self):
        self.assertEqual(grade(self.pid, self.trace("Merged.", "git merge json-output"), self.case)["verdict"], INCONCLUSIVE)


class WhyNamesUnreadPrs(unittest.TestCase):
    pid = "x2-why-names-unread-prs"

    def setUp(self):
        self.case = load_case("x2-why-no-gh")

    def trace(self, reply, gh_ok=False):
        events = [*bash(10, "git log --oneline -5 -- relay/retry.py"), *bash(20, "gh pr view 38 --json title,body", ok=gh_ok,
                                                                         head="" if gh_ok else "bash: gh: command not found")]
        return minimal(events=[*events, text(30, reply)], final_reply=reply)

    def test_a_reply_that_marks_the_prs_unread_passes(self):
        reply = "The limit went to five for the nightly rebuild.\n\n## Sources consulted\n- git log and blame\n- PRs #38 and #52: unread, gh is not installed here"
        self.assertEqual(grade(self.pid, self.trace(reply), self.case)["verdict"], PASS)

    def test_a_reply_silent_on_the_prs_fails(self):
        reply = "The limit went to five for the nightly rebuild.\n\n## Sources consulted\n- git log and blame"
        self.assertEqual(grade(self.pid, self.trace(reply), self.case)["verdict"], FAIL)

    def test_a_working_gh_is_inconclusive(self):
        self.assertEqual(grade(self.pid, self.trace("Per PR #38 the rebuild...", gh_ok=True), self.case)["verdict"], INCONCLUSIVE)

    def test_a_bare_pr_mention_goes_to_a_reader(self):
        result = grade(self.pid, self.trace("PR #38 raised the limit; PR #52 stopped retrying malformed feeds."), self.case)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))


class Projects(unittest.TestCase):
    def test_each_case_builds_its_project(self):
        for cid in CASES:
            with self.subTest(case=cid), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / "p"
                live.make_project(live.load_case(cid), project)
                self.assertTrue((project / ".git").is_dir())

    def test_the_json_branch_passes_its_tests_and_crashes_on_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            live.make_project(live.load_case("x2-verify-no-app-skill"), project)
            branch = subprocess.run(["git", "-C", str(project), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "json-output")
            env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}
            tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=project, env=env, capture_output=True, text=True)
            self.assertEqual(tests.returncode, 0, tests.stderr)
            cli = subprocess.run([sys.executable, "-m", "tally", "sample.txt", "--json"], cwd=project, env=env, capture_output=True, text=True)
            self.assertIn("AttributeError", cli.stderr)

    def test_the_overlay_breaks_the_plan_script(self):
        case = live.load_case("x2-plan-script-broken")
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            live.install_tree("f859024e", skills)
            live.apply_overlays(case, skills)
            done = subprocess.run([sys.executable, str(skills / "poteto-mode/scripts/plan.py"), "feature", "--harness", "claude-code"],
                                  capture_output=True, text=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("No module named 'pstack_route_tables'", done.stderr)


class GuideAliases(unittest.TestCase):
    """A screen case reaches a guide oracle through an x id; the alias must grade exactly as the guide id does."""

    def test_each_alias_grades_like_its_guide_oracle(self):
        pairs = {"x-routes-to-expected-playbook": ("bug-prompt-routes-to-bug-fix", "x13-bugfix-keeps-accepted-input"),
                 "x2-failed-plan-worklist-opens-with-steps": ("worklist-opens-with-playbook-steps", "x2-plan-script-broken"),
                 "x2-failed-plan-local-branch-endpoint": ("default-endpoint-local-branch-without-remote", "x2-plan-script-broken")}
        traces = (minimal(events=bash(0, "git status") + [text(2, "Done.")], final_reply="Done."),
                  minimal(events=bash(0, PLAN, ok=False, head=PLAN_BROKE) + [text(2, "Fixed it.")], final_reply="Fixed it."))
        for alias, (guide, case_id) in pairs.items():
            case = load_case(case_id)
            for n, trace in enumerate(traces):
                with self.subTest(alias=alias, trace=n):
                    self.assertEqual(grade(alias, trace, case), grade(guide, trace, case))


if __name__ == "__main__":
    unittest.main()
