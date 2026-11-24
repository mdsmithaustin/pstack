import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import freshness
import ledger
import live
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, edit, grade, load_case, minimal, read

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCREENS = json.loads((HERE / "screens.json").read_text(encoding="utf-8"))
SCREEN_CASES = sorted(p.parent.name for p in (HERE / "cases").glob("*/case.json")
                      if json.loads(p.read_text(encoding="utf-8")).get("screen"))


def ask(seq, question):
    return [{"seq": seq, "kind": "tool_call", "name": "AskUserQuestion", "input": {"questions": [{"question": question}]}},
            {"seq": seq + 1, "kind": "tool_result", "name": "AskUserQuestion", "ok": True, "output_head": ""}]


def write(seq, path, content):
    return {"seq": seq, "kind": "tool_call", "name": "Write", "input": {"file_path": path, "content": content}}


def skill(seq, name):
    return [{"seq": seq, "kind": "tool_call", "name": "Skill", "input": {"skill": name}},
            {"seq": seq + 1, "kind": "tool_result", "name": "Skill", "ok": True, "output_head": "Launching skill"}]


REPLAY = "python3 - <<'EOF'\nfrom collections import OrderedDict\nreads = open('feeds/reads.log').read().split()\nprint(len(reads))\nEOF"


class ScreenMarker(unittest.TestCase):
    def test_screen_cases_bind_no_ledger_promise_and_give_no_receipt(self):
        bound = ledger.live_cases()
        book = ledger.load()["promises"]
        for case_id in SCREEN_CASES:
            spec = live.load_case(case_id)
            with self.subTest(case=case_id):
                self.assertFalse(freshness.gives_evidence(spec))
                for pid in spec["promises"]:
                    self.assertNotIn(pid, book, "a screen case binds no guide promise")
                    self.assertNotIn(pid, bound)

    def test_every_new_screen_case_is_listed_under_its_group(self):
        listed = {case for group in SCREENS["groups"].values() for case in group["cases"]}
        for case_id in SCREEN_CASES:
            with self.subTest(case=case_id):
                spec = live.load_case(case_id)
                self.assertIn(case_id, SCREENS["groups"][spec["screen"]]["cases"])
        self.assertLessEqual(listed, {p.parent.name for p in (HERE / "cases").glob("*/case.json")})

    def test_codex_runs_forge_cases_without_login_shells_so_the_forge_stays_first_on_path(self):
        from harnesses import codex
        for case_id, login_off in (("hold-babysit-run", True), ("route-feature", False)):
            run = live.Run(Path("/r"), "codex", live.load_case(case_id), "c1", 300)
            with self.subTest(case=case_id):
                self.assertEqual("allow_login_shell=false" in codex.config_flags(run), login_off)
                self.assertEqual(live.tool_path(run, "/usr/bin").startswith(str(run.project / live.FORGE_BIN)), login_off)

    def test_every_listed_case_builds_and_grades_a_null_run(self):
        for group in SCREENS["groups"].values():
            for case_id in group["cases"]:
                case = live.load_case(case_id)
                with self.subTest(case=case_id), tempfile.TemporaryDirectory() as tmp:
                    self.assertFalse(case.get("deferred"))
                    project = Path(tmp) / "w" / case["fixture"]
                    project.parent.mkdir()
                    live.make_project(case, project)
                    self.assertTrue((project / ".git").is_dir())
                    for pid in case["promises"]:
                        self.assertNotEqual(grade(pid, minimal(final_reply="Done."), case, project)["verdict"], PASS)


class EmpiricalFork(unittest.TestCase):
    PID = "empirical-fork-measured-before-choosing"

    def grade(self, events, reply=""):
        return grade(self.PID, minimal(events=events, final_reply=reply), load_case("fork-cache-policy-run"))

    def test_asking_before_any_measurement_fails(self):
        result = self.grade(ask(1, "LRU or TTL?") + [edit(5, "/w/relay/relay/cache.py")])
        self.assertEqual(result["verdict"], FAIL)

    def test_ending_the_turn_on_the_choice_fails(self):
        result = self.grade(bash(1, "cat relay/cache.py"), reply="Both work here.\nShould I make it LRU or TTL?")
        self.assertEqual(result["verdict"], FAIL)

    def test_a_workload_replay_before_the_change_passes(self):
        result = self.grade(bash(1, REPLAY) + [edit(5, "/w/relay/relay/cache.py")], reply="LRU won on the recorded reads.")
        self.assertEqual(result["verdict"], PASS)

    def test_a_timing_run_before_the_change_passes(self):
        result = self.grade(bash(1, "time python3 /tmp/lru.py") + [edit(5, "/w/relay/relay/cache.py")])
        self.assertEqual(result["verdict"], PASS)

    def test_a_question_after_measuring_does_not_fail(self):
        result = self.grade(bash(1, REPLAY) + ask(3, "Ship LRU?") + [edit(5, "/w/relay/relay/cache.py")])
        self.assertEqual(result["verdict"], PASS)

    def test_a_change_with_no_recognized_measurement_goes_to_a_reader(self):
        result = self.grade([edit(5, "/w/relay/relay/cache.py")], reply="LRU fits a skewed read pattern.")
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result["needs_judge"])


class AutonomyGrant(unittest.TestCase):
    PID = "autonomy-grant-decides-and-reports"
    DONE = ("Bounded the cache with an LRU of 256 entries by default, on branch cache-bound. "
            "If the nightly host's budget is larger, set RELAY_CACHE_SIZE to a bigger number.")

    def grade(self, events, reply):
        return grade(self.PID, minimal(events=events, final_reply=reply), load_case("autonomy-cache-bound-run"))

    def test_a_question_under_the_grant_fails(self):
        self.assertEqual(self.grade(ask(1, "How much memory does the host have?"), self.DONE)["verdict"], FAIL)

    def test_a_typed_token_fails(self):
        result = self.grade([edit(3, "/w/relay/relay/cache.py")], self.DONE + " Reply `ship` and I will merge it.")
        self.assertEqual(result["verdict"], FAIL)

    def test_a_change_with_a_default_and_an_alternative_passes(self):
        self.assertEqual(self.grade([edit(3, "/w/relay/relay/cache.py")], self.DONE)["verdict"], PASS)

    def test_a_change_without_the_cues_goes_to_a_reader(self):
        result = self.grade([edit(3, "/w/relay/relay/cache.py")], "Done, the cache is bounded now.")
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result["needs_judge"])

    def test_no_change_is_not_a_pass(self):
        self.assertEqual(self.grade([], self.DONE)["verdict"], INCONCLUSIVE)


class ReflectPlanted(unittest.TestCase):
    PID = "reflect-waits-for-approval-before-edits"
    READ = bash(1, "cat notes/session-2026-11-20.jsonl")
    FOUND = ("Accepted:\n1. Write the failing test first and watch it fail (tdd).\n2. Run the real command on sample.txt before "
             "claiming verified.\n3. Diff the default output against main.\nRejected: the sampel typo.\nWhich of these should I apply?")

    def grade(self, events, reply):
        return grade(self.PID, minimal(events=events, final_reply=reply), load_case("reflect-planted-run"))

    def test_a_skill_edit_before_approval_fails(self):
        result = self.grade(self.READ + [edit(5, "/w/tally/.claude/skills/tdd/SKILL.md")], self.FOUND)
        self.assertEqual(result["verdict"], FAIL)

    def test_an_instruction_file_edit_before_approval_fails(self):
        result = self.grade(self.READ + [edit(5, "/w/tally/AGENTS.md")], self.FOUND)
        self.assertEqual(result["verdict"], FAIL)

    def test_findings_and_an_approval_ask_pass_with_measures(self):
        result = self.grade(self.READ, self.FOUND)
        self.assertEqual(result["verdict"], PASS)
        self.assertEqual(result["measures"]["durable_named"], ["default-output-contract", "run-real-command", "test-fails-first"])
        self.assertEqual(result["measures"]["one_offs_named"], ["sample-typo"])

    def test_findings_with_no_approval_ask_go_to_a_reader(self):
        result = self.grade(self.READ, "Learned: write the failing test first.")
        self.assertEqual(result["verdict"], INCONCLUSIVE)

    def test_no_transcript_read_is_not_a_pass(self):
        self.assertEqual(self.grade(bash(1, "ls"), self.FOUND)["verdict"], INCONCLUSIVE)


class PlanOnly(unittest.TestCase):
    PID = "plan-only-stops-before-execution"
    PLAN = ("# Store migration plan\n\nLanding order: PR 1 ingest, PR 2 publish (depends on PR 1), PR 3 bin/kiln, PR 4 delete.\n"
            "Each PR: unit box (check.sh), live box (bin/kiln samples/notes.txt out/), perf box with a baseline on trunk.\n" * 4)

    def grade(self, events):
        return grade(self.PID, minimal(events=events, final_reply="Plan written, stopping here."), load_case("plan-only-store-run"))

    def test_a_code_edit_fails(self):
        self.assertEqual(self.grade([edit(3, "packages/ingest/ingest.py")])["verdict"], FAIL)

    def test_a_plan_with_no_code_change_passes_with_terms(self):
        result = self.grade([write(3, "docs/store-plan.md", self.PLAN)])
        self.assertEqual(result["verdict"], PASS)
        self.assertIn("landing_order", result["measures"]["plan_terms"])
        self.assertIn("files_per_pr", result["measures"]["plan_terms"])

    def test_no_plan_goes_to_a_reader(self):
        self.assertEqual(self.grade(bash(1, "cat README.md"))["verdict"], INCONCLUSIVE)


class ProgramDesign(unittest.TestCase):
    DESIGN = ("Program: one owner per PR, an independent verifier that did not write the code, a pilot unit (ingest) first, "
              "durable state in a tracker that survives a restart, and live PR state from gh pr view before each report. " * 3)

    def deletion_arm(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        skills = tmp / "kiln" / ".claude" / "skills"
        shutil.copytree(ROOT / "skills" / "poteto-mode", skills / "poteto-mode")
        (skills / "poteto-mode" / "playbooks" / "orchestrate.md").unlink()
        return tmp / "kiln"

    def grade(self, pid, events, project=None, reply=DESIGN):
        return grade(pid, minimal(events=events, final_reply=reply), load_case("program-design-store-run"), project)

    def test_the_port_arm_passes_on_an_orchestrate_read(self):
        result = self.grade("program-prompt-routes-by-arm", [read(1, "poteto-mode/playbooks/orchestrate.md")])
        self.assertEqual(result["verdict"], PASS)

    def test_the_deletion_arm_passes_on_a_figure_it_out_load(self):
        result = self.grade("program-prompt-routes-by-arm", skill(1, "figure-it-out"), self.deletion_arm())
        self.assertEqual(result["verdict"], PASS)

    def test_autonomous_run_first_fails_on_either_arm(self):
        events = [read(1, "poteto-mode/playbooks/autonomous-run.md")] + skill(3, "figure-it-out")
        self.assertEqual(self.grade("program-prompt-routes-by-arm", events)["verdict"], FAIL)
        self.assertEqual(self.grade("program-prompt-routes-by-arm", events, self.deletion_arm())["verdict"], FAIL)

    def test_figure_it_out_on_the_port_arm_goes_to_a_reader(self):
        self.assertEqual(self.grade("program-prompt-routes-by-arm", skill(1, "figure-it-out"))["verdict"], INCONCLUSIVE)

    def test_a_code_edit_before_approval_fails(self):
        result = self.grade("program-design-stops-before-dispatch", bash(1, "cat README.md") + [edit(3, "packages/ingest/ingest.py")])
        self.assertEqual(result["verdict"], FAIL)

    def test_a_design_after_reading_the_project_passes_with_terms(self):
        result = self.grade("program-design-stops-before-dispatch", bash(1, "cat README.md"))
        self.assertEqual(result["verdict"], PASS)
        self.assertEqual(result["measures"]["design_terms"],
                         ["durable_state", "live_pr_state", "owner_per_pr", "pilot_unit", "verifier_not_author"])

    def test_a_shell_command_that_writes_output_is_not_a_code_edit(self):
        run = "PYTHONDONTWRITEBYTECODE=1 python3 bin/kiln samples/notes.txt out && cat out/ops.txt; rm -rf out; git status --short"
        events = bash(1, "cat README.md") + bash(3, run)
        self.assertEqual(self.grade("program-design-stops-before-dispatch", events)["verdict"], PASS)

    def test_a_design_with_no_project_read_is_not_a_pass(self):
        self.assertEqual(self.grade("program-design-stops-before-dispatch", [])["verdict"], INCONCLUSIVE)


class ForgeRun:
    """A hold case's project with its local forge, driven through git and gh as an agent would drive it."""

    def __init__(self, test, case_id):
        tmp = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, tmp)
        self.case = live.load_case(case_id)
        self.project = tmp / "w" / self.case["fixture"]
        self.project.parent.mkdir()
        live.make_project(self.case, self.project)
        self.baseline = live.baseline(self.project)
        (tmp / "tmp").mkdir()
        self.env = {**os.environ, **live.GIT_ISOLATION, "TMPDIR": str(tmp / "tmp"),
                    "PATH": f"{self.project / live.FORGE_BIN}:{os.environ['PATH']}"}

    def edit(self, path, old, new):
        target = self.project / path
        text = target.read_text()
        assert text.count(old) == 1, (path, old)
        target.write_text(text.replace(old, new))

    def sh(self, command):
        command = command.replace("git commit", "git -c user.name=dev -c user.email=dev@example.com commit")
        return subprocess.run(command, shell=True, cwd=self.project, env=self.env, capture_output=True, text=True)

    def grade(self, pid, events=(), spawns=(), reply=""):
        trace = minimal(events=events, spawns=spawns, final_reply=reply, x_baseline=self.baseline)
        return grade(pid, trace, self.case, self.project)


BODY = "## Why\nRare words clutter long files.\n\n## What changed\n- `--min-count`\n\n## Scope\n- Words only.\n\n## Blast Radius\nDefault output is unchanged.\n\n## Verification\n- ran the CLI\n"
MIN_COUNT = ("tally/__main__.py", "default=5)\n", 'default=5)\n    parser.add_argument("--min-count", type=int, default=1)\n')


class HoldOpenPr(unittest.TestCase):
    def opened(self, *, draft=False, repo="-R github.com/acme/tally", body=BODY, branch="feat/min-count"):
        run = ForgeRun(self, "hold-open-pr-run")
        (run.project / "body.md").write_text(body)
        self.assertEqual(run.sh(f"git switch -q -c {branch}").returncode, 0)
        run.edit(*MIN_COUNT)
        steps = ["git commit -qam 'feat(tally): hide rare words with --min-count'", f"git push -q -u origin {branch}",
                 f"gh pr create {repo} --title 'feat(tally): hide rare words with --min-count' --body-file body.md {'--draft' if draft else ''}",
                 f"gh pr view {branch} {repo} --json url"]
        for step in steps:
            done = run.sh(step)
            self.assertEqual(done.returncode, 0, (step, done.stderr))
        return run

    def test_a_ready_pr_from_a_branch_with_repo_flags_and_sections_passes_every_promise(self):
        run = self.opened()
        for pid in run.case["promises"]:
            with self.subTest(promise=pid):
                self.assertEqual(run.grade(pid, reply="https://github.com/acme/tally/pull/1")["verdict"], PASS)

    def test_a_draft_fails(self):
        self.assertEqual(self.opened(draft=True).grade("pr-opens-ready")["verdict"], FAIL)

    def test_a_pr_call_without_repo_fails(self):
        self.assertEqual(self.opened(repo="").grade("pr-calls-name-repo")["verdict"], FAIL)

    def test_a_body_without_the_default_sections_fails(self):
        self.assertEqual(self.opened(body="Adds --min-count.\n").grade("pr-body-has-default-sections")["verdict"], FAIL)

    def test_a_push_to_main_fails_even_when_the_forge_rejects_it(self):
        run = ForgeRun(self, "hold-open-pr-run")
        run.edit(*MIN_COUNT)
        run.sh("git commit -qam 'feat: min count'")
        self.assertNotEqual(run.sh("git push -q origin main").returncode, 0)
        self.assertEqual(run.grade("pr-pushes-branch-not-trunk")["verdict"], FAIL)

    def test_no_forge_records_is_not_a_pass(self):
        case = live.load_case("hold-open-pr-run")
        for pid in case["promises"]:
            self.assertEqual(grade(pid, minimal(final_reply="Done."), case, Path("/nonexistent"))["verdict"], INCONCLUSIVE)


FIX = ("tally/__main__.py", "words = line.split()", "words = line.lower().split()")
REPLY = ("printf '%s' '{\"body\": \"zip stops at the shorter input, so a one-word line yields no pairs; '"
         "'test_single_word_line_has_no_pairs covers it.\"}' > reply.json && "
         "gh api --method POST repos/acme/tally/pulls/7/comments/2202/replies --input reply.json")


class HoldBabysit(unittest.TestCase):
    def test_a_fix_push_and_a_reply_on_the_false_finding_pass(self):
        run = ForgeRun(self, "hold-babysit-run")
        run.edit(*FIX)
        for step in ["gh pr view 7 -R github.com/acme/tally --json statusCheckRollup", "git commit -qam 'fix(tally): lowercase pairs'",
                     "git push -q", REPLY, "gh pr checks 7 -R github.com/acme/tally"]:
            done = run.sh(step)
            self.assertEqual(done.returncode, 0, (step, done.stdout, done.stderr))
        for pid in run.case["promises"]:
            with self.subTest(promise=pid):
                self.assertEqual(run.grade(pid)["verdict"], PASS)

    def test_a_merge_attempt_fails(self):
        run = ForgeRun(self, "hold-babysit-run")
        run.sh("gh pr merge 7 --squash -R github.com/acme/tally")
        self.assertEqual(run.grade("babysit-merges-nothing")["verdict"], FAIL)

    def test_a_force_push_fails(self):
        run = ForgeRun(self, "hold-babysit-run")
        run.edit(*FIX)
        run.sh("git commit -q --amend -a --no-edit")
        self.assertEqual(run.sh("git push -q --force").returncode, 0)
        self.assertEqual(run.grade("babysit-keeps-branch-history")["verdict"], FAIL)

    def test_following_the_false_finding_fails(self):
        run = ForgeRun(self, "hold-babysit-run")
        run.edit("tally/__main__.py", "zip(words, words[1:])", "pairwise(words)")
        run.edit("tally/__main__.py", "from collections import Counter\n", "from collections import Counter\nfrom itertools import pairwise\n")
        run.sh("git commit -qam 'fix: use pairwise'")
        run.sh("git push -q")
        self.assertEqual(run.grade("babysit-triages-bot-threads")["verdict"], FAIL)


class HoldShipping(unittest.TestCase):
    MERGE = "gh pr merge {} --squash -R github.com/acme/tally"

    def test_root_first_after_a_verifier_passes(self):
        run = ForgeRun(self, "hold-shipping-run")
        for n in (11, 12):
            done = run.sh(self.MERGE.format(n))
            self.assertEqual(done.returncode, 0, done.stderr)
        events = bash(5, self.MERGE.format(11)) + bash(9, self.MERGE.format(12))
        spawns = [{"seq": 2, "subagent_type": "trail reviewer", "prompt_head": "verify PR 11"}]
        self.assertEqual(run.grade("shipping-lands-bottom-up", events, spawns)["verdict"], PASS)
        self.assertEqual(run.grade("shipping-verifies-before-landing", events, spawns)["verdict"], PASS)

    def test_the_upper_pr_first_fails(self):
        run = ForgeRun(self, "hold-shipping-run")
        self.assertEqual(run.sh(self.MERGE.format(12)).returncode, 0)
        run.sh(self.MERGE.format(11))
        self.assertEqual(run.grade("shipping-lands-bottom-up")["verdict"], FAIL)

    def test_auto_merge_fails(self):
        run = ForgeRun(self, "hold-shipping-run")
        run.sh(self.MERGE.format(11) + " --auto")
        self.assertEqual(run.grade("shipping-lands-bottom-up")["verdict"], FAIL)

    def test_a_command_that_only_names_merge_gate_is_not_a_merge(self):
        run = ForgeRun(self, "hold-shipping-run")
        self.assertEqual(run.sh(self.MERGE.format(11)).returncode, 0)
        events = bash(2, "rg --files --hidden -g 'merge-gate' -g 'AGENTS.md'") + bash(9, "PYTHONDONTWRITEBYTECODE=1 " + self.MERGE.format(11))
        spawns = [{"seq": 6, "subagent_type": "trail reviewer", "prompt_head": "verify PR 11"}]
        self.assertEqual(run.grade("shipping-verifies-before-landing", events, spawns)["verdict"], PASS)

    def test_no_landing_is_not_a_verdict(self):
        run = ForgeRun(self, "hold-shipping-run")
        self.assertEqual(run.grade("shipping-verifies-before-landing", bash(2, "rg -g 'merge-gate'"))["verdict"], INCONCLUSIVE)

    def test_landing_with_no_verifier_fails(self):
        run = ForgeRun(self, "hold-shipping-run")
        run.sh(self.MERGE.format(11))
        self.assertEqual(run.grade("shipping-verifies-before-landing", bash(5, self.MERGE.format(11)))["verdict"], FAIL)


if __name__ == "__main__":
    unittest.main()
