"""Model-free controls for the four plan-route oracles: a known-good and a known-bad trace for each."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import oracles
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, edit, git_in, grade, load_case, make_repo, minimal, read, skill_call

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
PLAN = SKILLS / "poteto-mode" / "scripts" / "plan.py"
LOW = ('--consequence "low:text path untouched, read __main__.py" --reach "low:one entry point, found by grep" '
       '--uncertainty "low:the request states the flag and output" --complexity "low:git log shows one commit on the file" '
       '--reversibility "low:additive flag, a revert restores it"')
FACTS = {
    "lightweight": LOW,
    "standard": LOW.replace('--reach "low:one entry point, found by grep"', '--reach "material:three callers"'),
    "intensive": LOW.replace('--consequence "low:text path untouched, read __main__.py"', '--consequence "material:writes the store"')
                    .replace('--uncertainty "low:the request states the flag and output"', "--uncertainty unknown"),
}
RUN = 'python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/plan.py" feature --harness claude-code'
SOURCE, TEST = "/w/tally/tally/__main__.py", "/w/tally/tests/test_json.py"
ITEMS = ("feature playbook opening", "Risk and acceptance", "Build and prove", "Deliver with review status", "Reply")
CASE = load_case("feature-plan-route-run")


def plan_head(route):
    return f"playbook: feature (${{PSTACK_SKILLS_ROOT}}/poteto-mode/playbooks/feature.md)\nroute: {route} (table: all five facts are low with evidence)\n"


def plan(seq, route="lightweight", ok=True, args=None):
    facts = "" if route == "pending" else " " + (args or FACTS.get(route, LOW))
    return bash(seq, RUN + facts, ok=ok, head=plan_head(route) if ok else "plan.py: record all five facts")


def snapshot(seq, states, items=ITEMS, carrier="TodoWrite"):
    return {"seq": seq, "carrier": carrier, "items": [{"text": text, "state": state} for text, state in zip(items, states)]}


def kept_worklist(start):
    return [snapshot(start, ["in_progress"] + ["pending"] * 4), snapshot(start + 20, ["completed"] * 5)]


def good_events():
    return (plan(1, "pending") + plan(3) + skill_call(6, "spec-probes") + [edit(10, TEST), edit(12, SOURCE)]
            + skill_call(14, "principle-prove-it-works") + bash(16, "python3 -m tally sample.txt --json"))


def trace(events, worklist=(), reply="Added --json on branch feat/json-flag. Review with `git diff main..feat/json-flag`.", **extra):
    return minimal(events=events, worklist=list(worklist), final_reply=reply, **extra)


class PlanCalls(unittest.TestCase):
    def test_the_printed_loads_match_the_plan_script_on_every_routed_playbook_and_route(self):
        manifest = json.loads((SKILLS / "poteto-mode" / "routes.json").read_text(encoding="utf-8"))
        routed = [name for name, entry in manifest["playbooks"].items() if entry.get("tiered")]
        self.assertIn("feature", routed)
        for playbook in routed:
            for route in manifest["routes"]:
                with self.subTest(playbook=playbook, route=route):
                    argv = [sys.executable, str(PLAN), playbook, "--harness", "claude-code", "--project", str(ROOT)]
                    for flag, value in re.findall(r'(--\w+) (?:"([^"]+)"|\S+)', FACTS[route]):
                        argv += [flag, value or "unknown"]
                    out = subprocess.run(argv, capture_output=True, text=True, check=True).stdout
                    self.assertIn(f"route: {route} ", out)
                    printed = {}
                    for line in out.split("\ngates:")[0].splitlines():
                        item = re.match(r"(\d+)\. ", line)
                        if item:
                            number = int(item.group(1))
                        elif line.startswith("   load: "):
                            printed.setdefault(number, []).extend(oracles.PLAN_LOAD.findall(line))
                    derived = oracles.plan_step_loads(SKILLS, playbook, route)
                    self.assertEqual(sorted(skill for skills in printed.values() for skill in skills),
                                     sorted(skill for skills in derived.values() for skill in skills))

    def test_the_lightweight_feature_route_prints_the_two_kept_loads(self):
        self.assertEqual(oracles.plan_step_loads(SKILLS, "feature", "lightweight"), {4: ["spec-probes"], 7: ["principle-prove-it-works"]})

    def test_a_plan_call_is_read_through_wrappers_and_other_playbooks_are_ignored(self):
        events = (bash(1, f"cd /w/tally && PSTACK_SKILLS_ROOT=.claude/skills {RUN} {LOW} | tee /tmp/plan.txt", head=plan_head("lightweight"))
                  + bash(3, RUN.replace("feature", "bug-fix"), head=plan_head("standard"))
                  + bash(5, RUN + " --step 4 --route lightweight", head="feature step 4, from ..."))
        calls = oracles.plan_calls(oracles.View(trace(events), CASE, None), "feature")
        self.assertEqual([(c["seq"], c["route"], c["prints_plan"], c["steps"]) for c in calls],
                         [(1, "lightweight", True, []), (5, None, False, ["4"])])


class GraderSkillInputs(unittest.TestCase):
    """Live seed tally-v_6uk6dp: the grader's skills copy held no routes.json, so two oracles could not derive the plan."""

    def test_the_graders_skills_copy_carries_what_the_plan_oracles_read(self):
        import grade_boundary
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp).resolve() / "skills"
            grade_boundary._copy_skill_inputs(SKILLS, copy)
            self.assertEqual(oracles.plan_step_loads(copy, "feature", "lightweight"), oracles.plan_step_loads(SKILLS, "feature", "lightweight"))
            self.assertTrue(oracles.plan_step_loads(copy, "feature", "lightweight"))

    def test_a_skills_tree_without_a_route_manifest_still_copies(self):
        import grade_boundary
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp).resolve() / "source" / "poteto-mode"
            (source / "playbooks").mkdir(parents=True)
            (source / "SKILL.md").write_text("entry\n")
            (source / "playbooks" / "feature.md").write_text("1. **Built.** Done.\n")
            copy = Path(tmp).resolve() / "skills"
            grade_boundary._copy_skill_inputs(source.parent, copy)
            self.assertFalse((copy / "poteto-mode" / "routes.json").exists())
            self.assertIsNone(oracles.plan_step_loads(copy, "feature", "lightweight"))


class LeadPrintsPlan(unittest.TestCase):
    PID = "lead-prints-plan-before-edits"

    def test_a_routed_plan_before_the_first_write_passes(self):
        result = grade(self.PID, trace(good_events()), CASE)
        self.assertEqual((result["verdict"], result["measures"]), (PASS, {"route": "lightweight", "plan_calls": 2}), result)

    def test_an_edit_with_no_plan_fails(self):
        result = grade(self.PID, trace([edit(1, SOURCE)]), CASE)
        self.assertEqual((result["verdict"], result["failures"]),
                         (FAIL, [f"the lead wrote {SOURCE} at seq 1 with no routed plan returned before it"]))

    def test_a_pending_plan_a_failed_plan_or_a_late_plan_does_not_count(self):
        for name, events in (("pending only", plan(1, "pending") + [edit(3, SOURCE)]),
                             ("usage error", plan(1, ok=False) + [edit(3, SOURCE)]),
                             ("step text only", bash(1, RUN + " --step 4 --route lightweight", head="feature step 4") + [edit(3, SOURCE)]),
                             ("after the edit", [edit(1, SOURCE)] + plan(3))):
            with self.subTest(name):
                self.assertEqual(grade(self.PID, trace(events), CASE)["verdict"], FAIL)

    def test_no_plan_and_no_write_or_an_unreadable_head_is_inconclusive(self):
        hidden = bash(1, f"{RUN} {LOW} > /tmp/plan.txt", head="")
        for name, events in (("no plan", [read(1, "poteto-mode/playbooks/feature.md")]), ("output redirected", hidden)):
            with self.subTest(name):
                self.assertEqual(grade(self.PID, trace(events), CASE)["verdict"], INCONCLUSIVE)


class PlanStepLoads(unittest.TestCase):
    PID = "plan-step-loads-arrive-with-step"

    def test_both_printed_loads_in_time_pass_and_the_measures_report_the_run(self):
        events = good_events() + [read(18, "poteto-mode/SKILL.md"), read(19, "deslop/SKILL.md"), read(20, "how/SKILL.md")]
        events += bash(21, RUN + " --step 7 --route lightweight", head="feature step 7")
        result = grade(self.PID, trace(events), CASE)
        self.assertEqual(result["verdict"], PASS, result)
        measures = result["measures"]
        self.assertEqual((measures["route"], measures["entry_rereads"], measures["step_text_calls"], measures["unlisted_skill_loads"]),
                         ("lightweight", 1, ["7"], ["how"]))
        self.assertEqual(measures["loads"]["spec-probes"],
                         {"how": "skill-tool", "seq": 6, "returned": 7, "after_routed_plan": True, "before_first_code_write": True})

    def test_a_finished_run_that_never_loads_a_printed_skill_fails(self):
        events = plan(1) + skill_call(4, "spec-probes") + [edit(8, SOURCE)]
        result = grade(self.PID, trace(events), CASE)
        self.assertEqual((result["verdict"], result["failures"]), (FAIL, ["the finished run never loaded principle-prove-it-works"]))

    def test_a_pre_code_load_after_the_first_test_write_fails(self):
        events = plan(1) + [edit(4, TEST)] + skill_call(6, "spec-probes") + skill_call(8, "principle-prove-it-works")
        result = grade(self.PID, trace(events), CASE)
        self.assertEqual((result["verdict"], result["failures"]), (FAIL, [f"spec-probes had not returned when the lead wrote {TEST} at seq 4"]))

    def test_a_refused_skill_call_is_not_a_load(self):
        events = plan(1) + skill_call(4, "spec-probes", ok=False) + [edit(8, SOURCE)] + skill_call(10, "principle-prove-it-works")
        self.assertEqual(grade(self.PID, trace(events), CASE)["verdict"], FAIL)

    def test_the_standard_route_expects_its_own_loads(self):
        events = plan(1, "standard") + skill_call(4, "spec-probes") + [edit(8, SOURCE)] + skill_call(10, "principle-prove-it-works")
        result = grade(self.PID, trace(events), CASE)
        expected = {skill for skills in oracles.plan_step_loads(SKILLS, "feature", "standard").values() for skill in skills}
        self.assertGreater(len(expected), 2)
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(set(result["measures"]["loads"]), expected)

    def test_no_routed_plan_or_a_killed_run_is_inconclusive(self):
        killed = trace(plan(1) + skill_call(4, "spec-probes") + [edit(8, SOURCE)], exit_code=-9)
        for name, run in (("no plan", trace([edit(1, SOURCE)])), ("killed before the proof step", killed)):
            with self.subTest(name):
                self.assertEqual(grade(self.PID, run, CASE)["verdict"], INCONCLUSIVE)


class WorklistFollowsPlan(unittest.TestCase):
    PID = "worklist-follows-plan-and-is-kept"

    def test_a_worklist_made_from_the_plan_items_and_updated_passes(self):
        result = grade(self.PID, trace(good_events(), kept_worklist(5)), CASE)
        self.assertEqual(result["verdict"], PASS, result)

    def test_no_worklist_after_the_plan_fails(self):
        for name, worklist in (("none at all", []), ("only before the routed plan", [snapshot(2, ["in_progress"] + ["pending"] * 4)])):
            with self.subTest(name):
                result = grade(self.PID, trace(good_events(), worklist), CASE)
                self.assertEqual((result["verdict"], result["failures"]),
                                 (FAIL, ["the finished run has no worklist snapshot after the routed plan returned"]))

    def test_a_worklist_that_is_never_updated_fails(self):
        idle = [snapshot(5, ["pending"] * 5), snapshot(9, ["pending"] * 5)]
        result = grade(self.PID, trace(good_events(), idle), CASE)
        self.assertEqual((result["verdict"], result["failures"]), (FAIL, ["no worklist item changed state after the routed plan returned"]))

    def test_a_kept_worklist_with_other_item_names_needs_a_reader(self):
        names = ("Set up", "Write the flag", "Check output", "Commit", "Report")
        worklist = [snapshot(5, ["pending"] * 5, names), snapshot(25, ["completed"] * 5, names)]
        self.assertEqual(grade(self.PID, trace(good_events(), worklist), CASE)["verdict"], INCONCLUSIVE)

    def test_the_standard_route_needs_the_playbook_steps(self):
        shape = oracles.playbook_shape("feature", SKILLS)
        steps = ["feature playbook opening"] + [f"{step['n']}. {step['text']}" for step in shape["steps"]]
        events = plan(1, "standard") + [edit(8, SOURCE)]
        for names, verdict in ((steps, PASS), (ITEMS, INCONCLUSIVE)):
            with self.subTest(items=len(names)):
                worklist = [snapshot(5, ["pending"] * len(names), names), snapshot(25, ["completed"] * len(names), names)]
                self.assertEqual(grade(self.PID, trace(events, worklist), CASE)["verdict"], verdict)

    def test_an_unfinished_run_or_no_routed_plan_is_inconclusive(self):
        for name, run in (("killed", trace(good_events(), exit_code=-9)), ("no plan", trace([edit(1, SOURCE)], kept_worklist(5)))):
            with self.subTest(name):
                self.assertEqual(grade(self.PID, run, CASE)["verdict"], INCONCLUSIVE)


class DefaultEndpoint(unittest.TestCase):
    PID = "default-endpoint-local-branch-without-remote"

    def repo(self, tmp):
        project = make_repo(tmp, 1, {"tally/__main__.py": "print('text')\n"})
        trunk = subprocess.run(["git", "-C", str(project), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        self.assertIn(trunk, oracles.TRUNK_BRANCHES)
        return project

    def change(self, project, commit=True):
        (project / "tally/__main__.py").write_text("print('json')\n")
        if commit:
            git_in(project, "commit", "-qam", "feat: add --json")

    def grade(self, project, reply="Added --json on branch feat/json-flag. Review with `git diff main..feat/json-flag`.", **extra):
        return grade(self.PID, trace([], reply=reply, **extra), CASE, project)

    def test_a_commit_on_a_named_branch_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.repo(tmp)
            git_in(project, "checkout", "-qb", "feat/json-flag")
            self.change(project)
            result = self.grade(project)
            self.assertEqual((result["verdict"], result["measures"]), (PASS, {"reply_has_diff_command": True}), result)

    def test_an_uncommitted_change_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.repo(tmp)
            self.change(project, commit=False)
            result = self.grade(project)
            self.assertEqual((result["verdict"], result["failures"]),
                             (FAIL, ["the implementation paths changed but no commit after the baseline carries the change"]))

    def test_a_commit_on_trunk_or_an_unnamed_branch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.repo(tmp)
            self.change(project)
            self.assertIn("the change is committed only on the trunk branch", self.grade(project)["failures"][0])
            git_in(project, "checkout", "-qb", "feat/json-flag")
            result = self.grade(project, reply="Added the flag and committed it.")
            self.assertEqual(result["failures"], ["the final reply names none of the delivering branches ['feat/json-flag']"])

    def test_a_branch_with_leftover_edits_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.repo(tmp)
            git_in(project, "checkout", "-qb", "feat/json-flag")
            self.change(project)
            (project / "tally/__main__.py").write_text("print('json again')\n")
            self.assertEqual(self.grade(project)["failures"], ["the implementation paths still hold uncommitted changes"])

    def test_a_remote_no_change_or_an_unfinished_run_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.repo(tmp)
            self.assertEqual(self.grade(project)["verdict"], INCONCLUSIVE)
            self.change(project, commit=False)
            self.assertEqual(self.grade(project, exit_code=-9)["verdict"], INCONCLUSIVE)
            git_in(project, "remote", "add", "origin", "https://example.invalid/tally.git")
            self.assertEqual(self.grade(project)["verdict"], INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
