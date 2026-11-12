import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODE = ROOT / "skills/poteto-mode"
SCRIPT = MODE / "scripts/plan.py"
MANIFEST = json.loads((MODE / "routes.json").read_text(encoding="utf-8"))
EVIDENCE = {"consequence": "no data or auth path", "reach": "one caller by grep", "uncertainty": "spec has an example",
            "complexity": "two commits on file", "reversibility": "one revert undoes it"}
LOW = [part for name, text in EVIDENCE.items() for part in (f"--{name}", f"low:{text}")]


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd)


def plan(*args, cwd=None):
    done = run(*args, "--json", cwd=cwd)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def facts(**levels):
    merged = {**{name: f"low:{text}" for name, text in EVIDENCE.items()}, **levels}
    return [part for name, value in merged.items() for part in (f"--{name}", value)]


class RouteTable(unittest.TestCase):
    def test_all_low_with_evidence_is_lightweight(self):
        self.assertEqual(plan("feature", *LOW)["route"], "lightweight")

    def test_low_without_evidence_counts_as_unknown(self):
        result = plan("feature", *facts(reach="low"))
        self.assertEqual(result["facts"]["reach"]["level"], "unknown")
        self.assertEqual(result["route"], "standard")

    def test_unknown_never_yields_lightweight(self):
        for name in MANIFEST["facts"]:
            with self.subTest(fact=name):
                self.assertNotEqual(plan("bug-fix", *facts(**{name: "unknown"}))["route"], "lightweight")

    def test_one_material_fact_is_standard(self):
        self.assertEqual(plan("refactoring", *facts(reach="material:12 callers"))["route"], "standard")
        self.assertEqual(plan("refactoring", *facts(consequence="material:billing"))["route"], "standard")

    def test_harm_that_is_unclear_or_hard_to_undo_is_intensive(self):
        self.assertEqual(plan("feature", *facts(consequence="material:data", uncertainty="material:spec gap"))["route"], "intensive")
        self.assertEqual(plan("feature", *facts(consequence="material:data", reversibility="unknown"))["route"], "intensive")

    def test_no_facts_gives_a_pending_plan_that_opens_the_worklist(self):
        result = plan("feature")
        self.assertEqual(result["route"], "pending")
        self.assertIn("Record the five risk facts", run("feature").stdout)

    def test_bad_level_is_a_usage_error(self):
        done = run("feature", *facts(reach="tiny:x"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("low, material, unknown", done.stderr)


class Evidence(unittest.TestCase):
    def test_placeholder_evidence_does_not_buy_the_lightweight_route(self):
        for thin in ("ok", "x", "-", "n/a", "none", "fine", "unknown", "low", "trivial."):
            with self.subTest(evidence=thin):
                result = plan("feature", *facts(reach=f"low:{thin}"))
                self.assertEqual(result["facts"]["reach"]["level"], "unknown")
                self.assertNotEqual(result["route"], "lightweight")

    def test_all_placeholders_cannot_reach_lightweight(self):
        thin = [part for name in MANIFEST["facts"] for part in (f"--{name}", "low:ok")]
        self.assertEqual(plan("feature", *thin)["route"], "intensive")

    def test_a_repeated_flag_is_refused(self):
        done = run("feature", "--consequence", "material:billing table", *LOW)
        self.assertEqual(done.returncode, 2)
        self.assertIn("more than once", done.stderr)

    def test_some_facts_without_the_rest_is_an_error_not_a_guess(self):
        done = run("feature", "--reach", "low:one caller by grep")
        self.assertEqual(done.returncode, 2)
        self.assertIn("record all five facts", done.stderr)

    def test_an_abbreviated_flag_is_refused(self):
        self.assertEqual(run("feature", *LOW, "--raise", "standard", "--reason", "new module").returncode, 2)


class Overrides(unittest.TestCase):
    def test_lead_can_raise_with_a_reason(self):
        result = plan("feature", *LOW, "--raise-to", "standard", "--reason", "new to this module")
        self.assertEqual((result["route"], result["route_source"]), ("standard", "lead"))

    def test_lead_cannot_lower(self):
        done = run("feature", *facts(reach="material:x"), "--raise-to", "lightweight", "--reason", "small")
        self.assertEqual(done.returncode, 2)
        self.assertIn("not lower it", done.stderr)

    def test_raise_needs_a_reason(self):
        self.assertEqual(run("feature", *LOW, "--raise-to", "intensive").returncode, 2)

    def test_a_user_route_still_needs_the_facts(self):
        done = run("feature", "--user-route", "lightweight")
        self.assertEqual(done.returncode, 2)
        self.assertIn("record all five facts", done.stderr)

    def test_lowering_below_the_table_warns(self):
        lowered = plan("feature", *facts(consequence="material:writes the billing table"), "--user-route", "lightweight")
        self.assertEqual(lowered["route"], "lightweight")
        self.assertIn("below the table's", lowered["warning"])
        self.assertIn("warning:", run("feature", *facts(consequence="material:writes the billing table"), "--user-route", "lightweight").stdout)
        self.assertIsNone(plan("feature", *LOW, "--user-route", "intensive")["warning"])

    def test_a_user_route_and_a_raise_together_are_refused(self):
        done = run("feature", *LOW, "--user-route", "lightweight", "--raise-to", "intensive", "--reason", "billing")
        self.assertEqual(done.returncode, 2)
        self.assertIn("not both", done.stderr)

    def test_a_route_on_a_fixed_playbook_is_noted_not_applied(self):
        result = plan("babysit", "--user-route", "lightweight")
        self.assertEqual(result["route"], "standard")
        self.assertIn("does not apply", result["warning"])

    def test_user_sets_the_route_in_either_direction(self):
        lowered = plan("feature", *facts(consequence="material:data", uncertainty="unknown"), "--user-route", "lightweight")
        self.assertEqual((lowered["route"], lowered["route_source"]), ("lightweight", "user"))
        self.assertEqual(plan("feature", *LOW, "--user-route", "intensive")["route"], "intensive")


class Worklist(unittest.TestCase):
    def test_standard_steps_carry_the_playbook_outcome_sentences(self):
        result = plan("bug-fix", *facts(reach="material:x"))
        self.assertEqual([step["name"] for step in result["steps"]],
                         ["Reproduced", "Root-caused", "Repaired", "Proven", "Landed", "Published"])
        self.assertEqual(result["steps"][0]["outcome"],
                         "**Reproduced.** The defect fires on the matching surface, under your control, on demand.")

    def test_skills_a_step_names_without_a_load_sentence_are_still_shown(self):
        root_caused = plan("bug-fix", *facts(reach="material:x"))["steps"][1]
        self.assertEqual(root_caused["uses"], ["how", "why"])
        self.assertEqual(plan("bug-fix", *LOW)["steps"][1]["uses"], [])

    def test_fixed_procedures_keep_the_panels_their_steps_require(self):
        loads = lambda name: {skill for step in plan(name)["steps"] for skill in step["loads"] + step["conditional"]}
        self.assertIn("swarm", loads("autopilot-full"))
        self.assertIn("arena", loads("eval"))
        self.assertFalse(any(step["held_for_intensive"] for step in plan("autopilot-full")["steps"]))

    def test_a_full_read_playbook_with_steps_still_lists_them(self):
        result = plan("orchestrate")
        self.assertTrue(result["full_read"])
        self.assertEqual([step["name"] for step in result["steps"]][:3], ["Frame", "Install the runtime", "Pilot"])
        text = run("orchestrate").stdout
        self.assertIn("in full. Its steps index the sections after them.", text)
        self.assertIn("1. **Frame.**", text)
        self.assertNotIn("It has no numbered steps", text)

    def test_panels_load_only_on_intensive(self):
        standard = plan("feature", *facts(reach="material:x"))
        designed = next(step for step in standard["steps"] if step["name"] == "Designed")
        self.assertEqual(designed["held_for_intensive"], ["architect"])
        self.assertNotIn("architect", designed["loads"])
        intensive = plan("feature", *facts(consequence="material:x", uncertainty="material:y"))
        self.assertIn("architect", next(step for step in intensive["steps"] if step["name"] == "Designed")["loads"])

    def test_lightweight_loads_only_proof_skills(self):
        result = plan("feature", *LOW)
        loaded = {skill for step in result["steps"] for skill in step["loads"]}
        self.assertLessEqual(loaded, set(MANIFEST["lightweight_keeps"]))
        self.assertIn("spec-probes", loaded)
        self.assertIn("principle-prove-it-works", loaded)
        self.assertEqual([item["item"] for item in result["lightweight_worklist"]],
                         ["Risk and acceptance", "Build and prove", "Deliver with review status"])

    def test_text_says_the_plan_is_not_the_worklist_owner_and_names_loads_per_harness(self):
        claude = run("feature", *LOW, "--harness", "claude-code").stdout
        codex = run("feature", *LOW, "--harness", "codex").stdout
        self.assertIn("Call the Skill tool with `spec-probes`", claude)
        self.assertIn('read "${PSTACK_SKILLS_ROOT:?}/spec-probes/SKILL.md" in full', codex)

    def test_a_load_behind_a_condition_is_not_printed_as_binding(self):
        steps = {step["name"]: step for step in plan("code-review")["steps"]}
        self.assertIn("interrogate", steps["Correctness checked"]["conditional"])
        self.assertNotIn("interrogate", steps["Correctness checked"]["loads"])
        self.assertIn("principle-boundary-discipline", steps["Boundaries checked"]["loads"])
        text = run("code-review").stdout
        self.assertIn("load only when the step's own condition holds: interrogate", text)

    def test_the_reply_line_and_its_loads_are_printed(self):
        feature = plan("feature", *LOW)
        self.assertTrue(feature["reply"].startswith("**Reply:** what you built"))
        self.assertIn("Last item, the reply. **Reply:**", run("feature", *LOW).stdout)
        autopilot = plan("autopilot-full")
        self.assertEqual(autopilot["reply_loads"], ["ketchup"])
        self.assertIn("Call the Skill tool with `ketchup`", run("autopilot-full", "--harness", "claude-code").stdout.split("Last item, the reply.")[1])

    def test_the_playbook_path_is_portable(self):
        result = plan("feature", *LOW)
        self.assertEqual(result["file"], "${PSTACK_SKILLS_ROOT}/poteto-mode/playbooks/feature.md")
        self.assertNotIn(str(ROOT), run("feature", *LOW).stdout)

    def test_fixed_procedure_playbook_needs_no_facts(self):
        result = plan("babysit")
        self.assertEqual((result["route"], result["route_source"]), ("standard", "fixed"))
        self.assertIsNone(result["scrutiny"])

    def test_index_shaped_playbook_is_read_in_full(self):
        self.assertIn("in full. It has no numbered steps.", run("opening-a-pr").stdout)

    def test_unknown_playbook_is_a_usage_error(self):
        self.assertEqual(run("nope").returncode, 2)


class OneStep(unittest.TestCase):
    def test_step_prints_that_step_and_no_other(self):
        done = run("bug-fix", "--step", "2", "--route", "standard")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("2. **Root-caused.** One mechanism explains the symptom", done.stdout)
        self.assertIn("rule them out until one survives", done.stdout)
        self.assertNotIn("**Reproduced.**", done.stdout)
        self.assertNotIn("**Repaired.**", done.stdout)

    def test_step_keeps_indented_sub_items(self):
        text = run("feature", "--step", "5").stdout
        for label in ("Blocking first steps", "Independent workstreams", "Shared mutable state", "Smallest safe decomposition"):
            self.assertIn(label, text)
        self.assertNotIn("**Built.**", text)

    def test_step_text_is_the_playbook_text(self):
        source = (MODE / "playbooks/perf-issue.md").read_text(encoding="utf-8")
        line = next(line for line in source.split("\n") if line.startswith("4. "))
        self.assertIn(line, run("perf-issue", "--step", "4").stdout)

    def test_lightweight_step_says_what_to_skip(self):
        self.assertIn("Lightweight route: do this step's work yourself.", run("bug-fix", "--step", "3", "--route", "lightweight").stdout)
        self.assertNotIn("Lightweight route", run("bug-fix", "--step", "3", "--route", "intensive").stdout)

    def test_the_lightweight_banner_keeps_the_independent_scrutiny_step(self):
        banner = run("feature", "--step", "7", "--route", "lightweight")
        self.assertEqual(banner.returncode, 0, banner.stderr)
        self.assertIn("the independent scrutiny the plan lists", banner.stdout)
        self.assertNotIn("spawn a subagent", banner.stdout)

    def test_a_route_banner_never_appears_on_a_fixed_playbook(self):
        for name, step in (("hillclimb", "5"), ("research", "1"), ("babysit", "1")):
            lightweight = run(name, "--step", step, "--route", "lightweight")
            standard = run(name, "--step", step, "--route", "standard")
            self.assertEqual((lightweight.returncode, standard.returncode), (0, 0), name)
            self.assertNotIn("Lightweight route", lightweight.stdout, name)
            self.assertNotIn("stay unloaded", standard.stdout, name)

    def test_missing_step_and_unknown_playbook_are_usage_errors(self):
        self.assertEqual(run("bug-fix", "--step", "9").returncode, 2)
        self.assertEqual(run("nope", "--step", "1").returncode, 2)

    def test_the_plan_names_the_step_command_with_its_route(self):
        self.assertIn("`bug-fix --step <number> --route standard`", run("bug-fix", *facts(reach="material:x")).stdout)
        self.assertIn("(steps 1, 2, 4)", run("feature", *LOW).stdout)
        self.assertNotIn("--step", run("opening-a-pr").stdout)


class BindingRegime(unittest.TestCase):
    def test_outcome_first_playbooks_allow_another_route_but_keep_limits(self):
        for text in (run("code-review").stdout, run("code-review", "--step", "10").stdout):
            self.assertIn("Outcome-first playbook: each step's bold outcome and its defining sentence bind.", text)
            self.assertIn("Every prohibition, authorization limit, and confidentiality rule in a step binds.", text)

    def test_other_playbooks_are_followed_as_written(self):
        for name in ("babysit", "visual-parity", "autonomous-run", "shipping"):
            for text in (run(name).stdout,):
                self.assertIn("Follow each step of this playbook as written.", text, name)
                self.assertNotIn("default route", text, name)
                self.assertIn("Every prohibition, authorization limit, and confidentiality rule", text, name)
        self.assertIn("Follow each step of this playbook as written.", run("babysit", "--step", "1").stdout)

    def test_every_outcome_first_step_opens_with_a_bold_outcome_and_a_sentence(self):
        self.assertEqual(len(MANIFEST["outcome_first"]), 11)
        for name in MANIFEST["outcome_first"]:
            for line in (MODE / "playbooks" / f"{name}.md").read_text(encoding="utf-8").split("\n"):
                if re.match(r"\d+\. ", line):
                    self.assertRegex(line, r"^\d+\. \*\*[A-Z][^*`(]*\.\*\* \S", f"{name}: {line[:60]}")


class GatesAndEndpoint(unittest.TestCase):
    def test_cleanup_runs_per_published_head_except_on_intensive(self):
        light = {gate["id"]: gate["when"] for gate in plan("feature", *LOW)["gates"]}
        heavy = {gate["id"]: gate["when"] for gate in plan("feature", *facts(consequence="material:x", uncertainty="unknown"))["gates"]}
        self.assertEqual(light["cleanup"], "before each push or published head")
        self.assertEqual(heavy["cleanup"], "before every commit or amend")
        self.assertEqual(light["preserve"], "before every commit")

    def test_recap_is_opt_in(self):
        recap = next(gate for gate in plan("feature", *LOW)["gates"] if gate["id"] == "recap")
        self.assertIn("only when the user or the repository", recap["when"])

    def test_every_playbook_gets_the_preserve_gate(self):
        for name in ("investigation", "babysit", "opening-a-pr", "feature"):
            args = LOW if name == "feature" else []
            self.assertIn("preserve", [gate["id"] for gate in plan(name, *args)["gates"]], name)
        self.assertEqual([gate["id"] for gate in plan("investigation")["gates"]], ["preserve", "reply-prose"])

    def test_a_playbook_that_changes_nothing_gets_no_publication_endpoint(self):
        for name in ("investigation", "code-review", "research"):
            result = plan(name)
            self.assertEqual(result["default_endpoint"], "what this playbook's Reply line names", name)
            self.assertNotIn("PR", result["default_endpoint"], name)

    def test_endpoint_follows_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            bare = plan("feature", *LOW, "--project", directory)
            self.assertIn("git init", bare["default_endpoint"])
            subprocess.run(["git", "init", "-q", directory], check=True)
            local = plan("feature", *LOW, "--project", directory)
            self.assertIn("local branch", local["default_endpoint"])
            self.assertIn("No remote", local["scrutiny"])
            subprocess.run(["git", "-C", directory, "remote", "add", "origin", "https://example.invalid/r.git"], check=True)
            self.assertIn("PR", plan("feature", *LOW, "--project", directory)["default_endpoint"])

    def test_every_code_step_that_runs_opening_a_pr_keeps_its_commits(self):
        line = "   still commit when the push or PR is skipped"
        for name, entry in MANIFEST["playbooks"].items():
            args = facts(reach="material:shared caller") if entry.get("tiered") else []
            steps = [step for step in plan(name, *args)["steps"] if step["runs_pr"]]
            with self.subTest(playbook=name):
                self.assertTrue(steps, "a code playbook needs a step that runs Opening a PR")
                text = run(name, *args).stdout.split("\n")
                for step in steps:
                    at = next(index for index, row in enumerate(text) if row.startswith(f"{step['number']}. "))
                    self.assertEqual(text[at + 1], line)
        self.assertIn(line, run("feature", *LOW).stdout, "the lightweight grouped worklist keeps the line")

    def test_a_playbook_that_changes_no_code_gets_no_commit_line(self):
        for name in ("babysit", "shipping", "investigation", "autopilot-full"):
            with self.subTest(playbook=name):
                self.assertFalse(any(step["runs_pr"] for step in plan(name)["steps"]))
                self.assertNotIn("still commit", run(name).stdout)

    def test_the_router_owns_the_commit_rule_for_a_skipped_pr(self):
        routes = (MODE / "references/routes.md").read_text(encoding="utf-8")
        self.assertIn("A skipped push or PR never skips that step's commits.", routes)


class Manifest(unittest.TestCase):
    def test_manifest_lists_only_playbooks_that_exist_and_need_a_flag(self):
        on_disk = {path.stem for path in (MODE / "playbooks").glob("*.md")}
        self.assertLessEqual(set(MANIFEST["playbooks"]), on_disk)
        for name, entry in MANIFEST["playbooks"].items():
            self.assertTrue(entry, f"{name} has no flag, so it needs no manifest entry")
            self.assertNotIn("file", entry)

    def test_a_playbook_without_a_manifest_entry_still_plans(self):
        self.assertNotIn("babysit", MANIFEST["playbooks"])
        self.assertEqual(plan("babysit")["route"], "standard")

    def test_the_manifest_holds_no_outcome_text(self):
        outcomes = [step["outcome"] for name in ("feature", "bug-fix") for step in plan(name, *facts(reach="material:x"))["steps"]]
        raw = (MODE / "routes.json").read_text(encoding="utf-8")
        for sentence in outcomes:
            self.assertNotIn(sentence.split("** ", 1)[1][:40], raw)

    def test_every_named_skill_exists(self):
        named = set(MANIFEST["panels"]) | set(MANIFEST["lightweight_keeps"]) | {gate["skill"] for gate in MANIFEST["gates"] if gate.get("skill")}
        for skill in named:
            self.assertTrue((ROOT / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_lightweight_worklist_and_skips_name_real_steps(self):
        for name, entry in MANIFEST["playbooks"].items():
            steps = {step["name"] for step in plan(name, *LOW)["steps"]} if entry.get("tiered") else set()
            named = [step for item in entry.get("lightweight_worklist", []) for step in item["covers"]] + list(entry.get("lightweight_skips", {}))
            for step in named:
                self.assertIn(step, steps, f"{name}: {step}")

    def test_routed_playbooks_delegate_only_where_the_spawn_rule_calls_for_it(self):
        for name in ("bug-fix", "refactoring", "perf-issue"):
            text = (MODE / "playbooks" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("(../references/delegation.md)'s spawn rule calls for one", text, name)
        self.assertIn("**Spawn up or out, never sideways.**", (MODE / "references/delegation.md").read_text(encoding="utf-8"))

    def test_the_panel_limit_names_the_four_routed_playbooks(self):
        triggers = (MODE / "references/task-triggers.md").read_text(encoding="utf-8")
        line = next(line for line in triggers.split("\n") if line.startswith("- Code that crosses"))
        self.assertIn("In Bug fix, Feature, Refactoring, and Perf issue this applies on the intensive route only.", line)

    def test_a_sandbox_alone_is_not_a_gated_repository(self):
        text = (MODE / "playbooks/opening-a-pr.md").read_text(encoding="utf-8")
        self.assertIn("`SANDBOX_NAME` alone does not make it gated.", text)
        self.assertIn("before the first commit, amend, push, PR operation, rebase, or merge preparation", text)

    def test_tiered_playbooks_cite_routes_and_scrutiny(self):
        for name, entry in MANIFEST["playbooks"].items():
            if entry.get("tiered"):
                text = (MODE / "playbooks" / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn("../references/routes.md", text, name)
                self.assertIn("../references/review-lens.md#independent-scrutiny", text, name)

    def test_a_lead_without_the_script_is_still_sent_to_the_gates_endpoint_and_scrutiny(self):
        triggers = (MODE / "references/task-triggers.md").read_text(encoding="utf-8")
        line = next(line for line in triggers.split("\n") if line.startswith("- A gate the plan prints"))
        self.assertIn("With no plan, run cleanup before every commit or amend", line)
        self.assertIn("(routes.md#endpoint)", line)
        self.assertIn("(review-lens.md#independent-scrutiny)", line)
        self.assertIn("## Endpoint", (MODE / "references/routes.md").read_text(encoding="utf-8"))
        self.assertIn("## Independent scrutiny", (MODE / "references/review-lens.md").read_text(encoding="utf-8"))

    def test_entry_and_more_playbooks_list_every_playbook(self):
        listed = set()
        for doc in (MODE / "SKILL.md", MODE / "references/playbooks.md"):
            listed |= set(re.findall(r"`playbooks/([a-z-]+)\.md`", doc.read_text(encoding="utf-8")))
        self.assertEqual(listed, {path.stem for path in (MODE / "playbooks").glob("*.md")})
        self.assertLess(len(re.findall(r"`playbooks/([a-z-]+)\.md`", (MODE / "SKILL.md").read_text(encoding="utf-8"))), len(listed))

    def test_step_titles_name_outcomes_not_skills(self):
        for name in ("feature", "bug-fix", "refactoring", "perf-issue"):
            for line in (MODE / "playbooks" / f"{name}.md").read_text(encoding="utf-8").split("\n"):
                title = re.match(r"\d+\. \*\*([^*]+)\*\*", line)
                if title:
                    self.assertNotIn("`", title.group(1), f"{name}: {title.group(1)}")
                    self.assertNotIn("(", title.group(1), f"{name}: {title.group(1)}")

if __name__ == "__main__":
    unittest.main()
