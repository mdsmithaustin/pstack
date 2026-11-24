import importlib.util
import json
import ntpath
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_a_pending_plan_already_binds_the_lightest_gates(self):
        pending, lightest = plan("feature"), plan("feature", *LOW)
        self.assertEqual(pending["route"], "pending")
        self.assertEqual(pending["gates"], lightest["gates"])
        self.assertIn("preserve", [gate["id"] for gate in pending["gates"]])
        text = run("feature").stdout
        for line in run("feature", *LOW).stdout.splitlines():
            if line.startswith("- preserve:"):
                self.assertIn(line, text)
                break
        else:
            self.fail("the lightweight plan prints no preserve gate line")

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


class EvidenceWords(unittest.TestCase):
    def test_evidence_made_only_of_filler_negation_or_counts_counts_as_unknown(self):
        for thin in ("not checked", "no evidence", "did not check", "ok ok ok", "ok, fine", "trust me", "nothing to check",
                     "not applicable", "unknown, tbd", "none, n/a", "n/a n/a n/a", "- - - - -", "one file, 3 lines"):
            with self.subTest(evidence=thin):
                result = plan("bug-fix", *facts(consequence=f"low:{thin}"))
                self.assertEqual(result["facts"]["consequence"]["level"], "unknown")
                self.assertEqual(result["route"], "standard")

    def test_evidence_that_says_nothing_was_checked_counts_as_unknown(self):
        for thin in ("not checked yet", "haven't checked", "not checked callers by grep", "not yet checked", "did not look",
                     "never looked", "not verified yet", "didn't test", "not tested", "skipped review", "didn’t check"):
            with self.subTest(evidence=thin):
                self.assertEqual(plan("bug-fix", *facts(consequence=f"low:{thin}"))["route"], "standard")

    def test_change_counts_alone_count_as_unknown(self):
        for thin in ("1 file changed, 3 insertions(+), 1 deletion(-)", "3 lines changed", "two files touched", "one change",
                     "two changes", "one insertion", "two deletions", "120 loc changed", "1 file / 3 lines", "1 file and 3 lines"):
            with self.subTest(evidence=thin):
                result = plan("bug-fix", *facts(consequence=f"low:{thin}"))
                self.assertEqual(result["facts"]["consequence"]["level"], "unknown")
                self.assertEqual(result["route"], "standard")

    def test_each_filler_word_alone_with_other_filler_counts_as_unknown(self):
        for thin in ("okay, na", "yes, low", "same files", "it is trivial", "no, didn't", "no, never", "unchecked, unknown",
                     "verified ok", "unverified, tbd", "one line", "two lines", "three files", "four lines", "five files",
                     "six lines", "seven files", "eight lines", "nine files", "ten lines", "checked it", "did nothing"):
            with self.subTest(evidence=thin):
                self.assertEqual(plan("bug-fix", *facts(consequence=f"low:{thin}"))["route"], "standard")

    def test_evidence_that_names_what_was_checked_stays_low(self):
        for evidence in (*EVIDENCE.values(), "one caller in cli.py, found by grep", "fixed evidence text",
                         "text path untouched, read __main__.py", "git log shows one commit on the file",
                         "checked callers by grep", "reviewed the diff of cli.py", "tests pass on main"):
            with self.subTest(evidence=evidence):
                self.assertEqual(plan("bug-fix", *facts(consequence=f"low:{evidence}"))["route"], "lightweight")


class EvidenceUsageErrors(unittest.TestCase):
    def test_every_value_flag_is_refused_when_repeated(self):
        cases = {
            "--raise-to": ("feature", *LOW, "--raise-to", "intensive", "--reason", "a", "--raise-to", "lightweight"),
            "--reason": ("feature", *LOW, "--raise-to", "intensive", "--reason", "a", "--reason", "b"),
            "--user-route": ("feature", *LOW, "--user-route", "intensive", "--user-route", "lightweight"),
            "--harness": ("feature", *LOW, "--harness", "codex", "--harness", "claude-code"),
            "--step": ("feature", "--step", "2", "--step", "3", "--route", "standard"),
            "--route": ("feature", "--step", "3", "--route", "intensive", "--route", "lightweight"),
        }
        for flag, args in cases.items():
            with self.subTest(flag=flag):
                done = run(*args)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertEqual(done.stdout, "")
                self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
                self.assertIn(f"{flag} was given more than once", done.stderr)

    def test_an_unknown_or_mistyped_flag_points_to_help_on_one_line(self):
        cases = {
            "--raise-too": ("feature", *LOW, "--raise-too", "standard"),
            "--reversability": ("feature", "--reversability", "low:one revert undoes it"),
            "--steps": ("feature", "--steps", "3"),
            "--bogus": ("feature", "--bogus"),
        }
        for flag, args in cases.items():
            with self.subTest(flag=flag):
                done = run(*args)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertEqual(done.stdout, "")
                self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
                self.assertIn(flag, done.stderr)
                self.assertIn("--help", done.stderr)

    def test_an_argument_that_is_not_utf8_is_a_usage_error(self):
        cases = {
            "fact": ("bug-fix", *facts(consequence=b"low:caf\xe9 caller found by grep")),
            "reason": ("feature", *LOW, "--raise-to", "standard", "--reason", b"caf\xe9 is new"),
        }
        for name, args in cases.items():
            with self.subTest(argument=name):
                done = run(*args)
                self.assertEqual(done.returncode, 2, done.stderr[-200:])
                self.assertIn("not valid UTF-8", done.stderr)
                self.assertNotIn("Traceback", done.stderr)


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


class OverrideUsageErrors(unittest.TestCase):
    def test_a_reason_without_a_raise_is_refused(self):
        cases = {
            "with facts": ("feature", *facts(consequence="material:billing", uncertainty="unknown"), "--reason", "x"),
            "before facts": ("feature", "--reason", "x"),
            "with a user route": ("feature", *LOW, "--user-route", "intensive", "--reason", "x"),
            "one procedure": ("babysit", "--reason", "x"),
        }
        for name, args in cases.items():
            with self.subTest(case=name):
                done = run(*args)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertIn("--reason goes with --raise-to", done.stderr)

    def test_a_blank_reason_counts_as_missing(self):
        for reason in ("", "  "):
            with self.subTest(reason=reason):
                done = run("feature", *LOW, "--raise-to", "standard", "--reason", reason)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertIn("--raise-to needs --reason", done.stderr)

    def test_risk_facts_on_a_playbook_with_one_procedure_are_refused(self):
        for args in (("--reach", "tiny:x"), tuple(LOW)):
            with self.subTest(args=args[:2]):
                done = run("babysit", *args)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertIn("takes no risk facts", done.stderr)


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

    def test_a_step_ends_at_the_next_heading(self):
        close = plan("orchestrate")["steps"][-1]
        self.assertEqual(close["name"], "Close")
        self.assertEqual(close["loads"] + close["conditional"] + close["uses"], [])
        self.assertNotIn("load", run("orchestrate").stdout.split("7. **Close.**")[1].split("gates:")[0])

    def test_panels_load_only_on_intensive(self):
        standard = plan("feature", *facts(reach="material:x"))
        designed = next(step for step in standard["steps"] if step["name"] == "Designed")
        self.assertEqual(designed["held_for_intensive"], ["architect"])
        self.assertNotIn("architect", designed["loads"])
        intensive = plan("feature", *facts(consequence="material:x", uncertainty="material:y"))
        self.assertIn("architect", next(step for step in intensive["steps"] if step["name"] == "Designed")["conditional"])

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
        result = plan("shipping")
        self.assertEqual((result["route"], result["route_source"]), ("standard", "fixed"))
        self.assertIsNone(result["scrutiny"])

    def test_index_shaped_playbook_is_read_in_full(self):
        self.assertIn("in full. It has no numbered steps.", run("opening-a-pr").stdout)

    def test_unknown_playbook_is_a_usage_error(self):
        self.assertEqual(run("nope").returncode, 2)


class ConditionalLoads(unittest.TestCase):
    maxDiff = None
    LOAD = re.compile(r"Skill tool with `([a-z0-9-]+)`")
    SENTENCE = re.compile(r"(?<=[.!?])\s+")
    CONDITION = re.compile(r"^\W*(?:In|For)\b|\b(?:if|when|whenever|unless|once|where|otherwise)\b"
                           r"|\bonly (?:when|if|for|on|in)\b|\s+only[.!?]?$"
                           r"|\bon the (?:lightweight|standard|intensive) route\b|\bor call the Skill tool\b", re.I)

    def test_no_playbook_prints_a_load_whose_sentence_names_a_condition_as_binding(self):
        spec = importlib.util.spec_from_file_location("route_plan", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        intensive = facts(consequence="material:x", uncertainty="material:y")
        wrong = []
        for path in sorted((MODE / "playbooks").glob("*.md")):
            tiered = MANIFEST["playbooks"].get(path.stem, {}).get("tiered", False)
            printed = {step["number"]: step["loads"] for step in plan(path.stem, *(intensive if tiered else []))["steps"]}
            for number, text in module.read_playbook(path)[1]:
                sentences = self.SENTENCE.split(text)
                plain = {skill for s in sentences if not self.CONDITION.search(s) for skill in self.LOAD.findall(s)}
                wrong += [f"{path.stem} step {number}: {skill}: {s}" for s in sentences if self.CONDITION.search(s)
                          for skill in self.LOAD.findall(s) if skill in printed[number] and skill not in plain]
        self.assertEqual(wrong, [], "Open a conditional load's sentence with its condition, such as "
                                    "\"When <condition>, call the Skill tool with `<name>`.\", so the plan prints it as conditional.")

    def test_the_plan_does_not_depend_on_which_sibling_skills_are_installed(self):
        args = ["bug-fix", *facts(reach="material:x"), "--project", "/"]
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(MODE, Path(tmp) / "skills/poteto-mode")
            alone = subprocess.run([sys.executable, str(Path(tmp) / "skills/poteto-mode/scripts/plan.py"), *args],
                                   capture_output=True, text=True)
        self.assertEqual(alone.returncode, 0, alone.stderr)
        self.assertEqual(alone.stdout, run(*args).stdout)

    def test_every_skill_a_step_names_exists_in_this_repository(self):
        intensive = facts(consequence="material:x", uncertainty="material:y")
        named = {skill for path in (MODE / "playbooks").glob("*.md")
                 for step in plan(path.stem, *(intensive if MANIFEST["playbooks"].get(path.stem, {}).get("tiered") else []))["steps"]
                 for skill in step["uses"]}
        self.assertTrue(named)
        self.assertEqual({skill for skill in named if not (ROOT / "skills" / skill / "SKILL.md").is_file()}, set())


class RenderedRules(unittest.TestCase):
    def test_every_route_prints_the_opening_prose(self):
        for name, entry in MANIFEST["playbooks"].items():
            if not entry.get("tiered"):
                continue
            for args in (LOW, facts(reach="material:shared caller")):
                with self.subTest(playbook=name, route=plan(name, *args)["route"]):
                    self.assertIn("   opening prose, kept with the first item: ", run(name, *args).stdout)
        self.assertIn("touches failure or recovery", run("feature", *LOW).stdout)

    def test_a_user_set_route_sends_a_raise_to_the_user(self):
        user = run("feature", *LOW, "--user-route", "lightweight").stdout
        self.assertNotIn("Otherwise raise the route.", user)
        self.assertIn("Otherwise ask the user to raise the route.", user)
        self.assertIn("Otherwise raise the route.", run("feature", *LOW).stdout)
        standard = run("feature", *facts(reach="material:shared caller"), "--user-route", "standard").stdout
        self.assertNotIn("Raise the route when you cannot choose.", standard)
        self.assertIn("Ask the user to raise the route when you cannot choose.", standard)
        self.assertIn("Raise the route when you cannot choose.", run("feature", *facts(reach="material:shared caller")).stdout)

    def test_the_plan_maps_the_skill_tool_phrase_off_claude_code(self):
        mapped = 'On this harness, "Call the Skill tool with `<name>`" means: read "${PSTACK_SKILLS_ROOT:?}/<name>/SKILL.md" in full.'
        self.assertIn(mapped, run("refactoring", *LOW, "--harness", "codex").stdout)
        for name in sorted(path.stem for path in (MODE / "playbooks").glob("*.md")):
            args = LOW if MANIFEST["playbooks"].get(name, {}).get("tiered") else []
            with self.subTest(playbook=name):
                codex = run(name, *args, "--harness", "codex").stdout
                self.assertEqual("call the skill tool" in codex.replace(mapped, "").lower(), mapped in codex)
                self.assertNotIn("On this harness", run(name, *args, "--harness", "claude-code").stdout)


class EntryPlanCommand(unittest.TestCase):
    BASE = "<this skill's base directory>"

    def command(self):
        entry = (MODE / "SKILL.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```sh\n(.*?)\n```", entry.split("print its plan", 1)[1], re.DOTALL)
        self.assertTrue(blocks, "the entry prints no plan command")
        return blocks[0]

    def test_filled_command_runs_from_another_directory_with_nothing_set(self):
        command = self.command()
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "installed skills"
            skills.mkdir()
            (skills / "poteto-mode").symlink_to(MODE, target_is_directory=True)
            elsewhere = Path(tmp) / "elsewhere"
            elsewhere.mkdir()
            filled = (command.replace(self.BASE, str(skills / "poteto-mode"))
                      .replace("<file-stem>", "feature")
                      .replace("<claude-code|codex|grok|hermes|other>", "claude-code")
                      .replace("python3", f'"{sys.executable}"', 1))
            env = {name: value for name, value in os.environ.items() if not name.startswith("PSTACK_")}
            done = subprocess.run(filled, shell=True, capture_output=True, text=True, cwd=elsewhere, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("playbook: feature"), done.stdout)
        self.assertIn("route: pending", done.stdout)


class OneStep(unittest.TestCase):
    def test_step_prints_that_step_and_no_other(self):
        done = run("bug-fix", "--step", "2", "--route", "standard")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("2. **Root-caused.** One mechanism explains the symptom", done.stdout)
        self.assertIn("rule them out until one survives", done.stdout)
        self.assertNotIn("**Reproduced.**", done.stdout)
        self.assertNotIn("**Repaired.**", done.stdout)

    def test_step_keeps_indented_sub_items(self):
        text = run("feature", "--step", "5", "--route", "standard").stdout
        for label in ("Blocking first steps", "Independent workstreams", "Shared mutable state", "Smallest safe decomposition"):
            self.assertIn(label, text)
        self.assertNotIn("**Built.**", text)

    def test_step_text_is_the_playbook_text(self):
        source = (MODE / "playbooks/perf-issue.md").read_text(encoding="utf-8")
        line = next(line for line in source.split("\n") if line.startswith("4. "))
        self.assertIn(line, run("perf-issue", "--step", "4", "--route", "standard").stdout)

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

    def test_step_prints_the_route_gates_for_recovery(self):
        standard = run("feature", "--step", "6", "--route", "standard", "--harness", "claude-code").stdout
        intensive = run("feature", "--step", "6", "--route", "intensive", "--harness", "claude-code").stdout
        for gate in ("- preserve: run", "- documentation: Call the Skill tool with `documentation-impact`", "- comments: Call the Skill tool with `no-comments`"):
            self.assertIn(gate, standard)
        self.assertIn("- cleanup: Call the Skill tool with `deslop`, before each push or published head.", standard)
        self.assertIn("- cleanup: Call the Skill tool with `deslop`, before every commit or amend.", intensive)
        investigation = run("investigation", "--step", "1").stdout
        self.assertIn("- preserve: run", investigation)
        self.assertNotIn("deslop", investigation)

    def test_step_maps_the_skill_tool_phrase_off_claude_code(self):
        codex = run("feature", "--step", "6", "--route", "standard", "--harness", "codex").stdout
        self.assertIn('means: read "${PSTACK_SKILLS_ROOT:?}/<name>/SKILL.md" in full.', codex)
        self.assertIn('- documentation: read "${PSTACK_SKILLS_ROOT:?}/documentation-impact/SKILL.md" in full', codex)
        self.assertNotIn("On this harness", run("feature", "--step", "6", "--route", "standard", "--harness", "claude-code").stdout)

    def test_lightweight_plan_says_item_numbers_are_not_step_numbers(self):
        hint = "Item numbers are not step numbers"
        self.assertIn(hint, run("feature", *LOW).stdout)
        self.assertNotIn(hint, run("feature", *facts(reach="material:x")).stdout)

    def test_missing_step_and_unknown_playbook_are_usage_errors(self):
        self.assertEqual(run("bug-fix", "--step", "9", "--route", "standard").returncode, 2)
        self.assertEqual(run("nope", "--step", "1").returncode, 2)

    def test_the_plan_names_the_step_command_with_its_route(self):
        self.assertIn("`bug-fix --step <number> --route standard`", run("bug-fix", *facts(reach="material:x")).stdout)
        self.assertIn("(steps 1, 2, 4)", run("feature", *LOW).stdout)
        self.assertNotIn("--step", run("opening-a-pr").stdout)


class StepRecovery(unittest.TestCase):
    KEPT = "Loads this route keeps from this step:"

    def test_a_step_that_runs_opening_a_pr_keeps_its_commits(self):
        line = "   still commit when the push or PR is skipped"
        for name, entry in MANIFEST["playbooks"].items():
            routes = ("lightweight", "standard") if entry.get("tiered") else ("standard",)
            args = facts(reach="material:shared caller") if entry.get("tiered") else []
            for step in plan(name, *args)["steps"]:
                for route in routes:
                    with self.subTest(playbook=name, step=step["number"], route=route):
                        printed = run(name, "--step", str(step["number"]), "--route", route).stdout
                        self.assertEqual(line in printed.split("\n"), step["runs_pr"])
        self.assertNotIn("still commit", run("babysit", "--step", "5").stdout)

    def test_a_lightweight_step_names_the_loads_the_route_keeps(self):
        for name, entry in MANIFEST["playbooks"].items():
            if not entry.get("tiered"):
                continue
            for step in plan(name, *LOW)["steps"]:
                with self.subTest(playbook=name, step=step["number"]):
                    printed = run(name, "--step", str(step["number"]), "--route", "lightweight", "--harness", "claude-code").stdout
                    body = printed.split("gates, which still bind:")[0].split("\n")
                    kept = [row for row in body if row.startswith(self.KEPT)]
                    if not re.search(r"call the skill tool with `[a-z0-9-]+`", "\n".join(row for row in body if row not in kept), re.I):
                        self.assertEqual(kept, [])
                        continue
                    self.assertEqual(len(kept), 1, printed)
                    named = re.findall(r"`([a-z0-9-]+)`", kept[0])
                    self.assertEqual(named, step["loads"])
                    if not named:
                        self.assertIn("none", kept[0])
        self.assertIn(f"{self.KEPT} none.", run("feature", "--step", "1", "--route", "lightweight").stdout)
        self.assertIn(f"{self.KEPT} `spec-probes`.", run("feature", "--step", "4", "--route", "lightweight").stdout)
        self.assertNotIn(self.KEPT, run("feature", "--step", "4", "--route", "standard").stdout)

    def test_a_lightweight_step_labels_its_conditional_loads_as_the_plan_does(self):
        label = "   load only when the step's own condition holds: "
        checked = 0
        for name, entry in MANIFEST["playbooks"].items():
            if not entry.get("tiered"):
                continue
            full = [row[len(label):].split(", ") for row in run(name, *LOW).stdout.split("\n") if row.startswith(label)]
            for step in plan(name, *LOW)["steps"]:
                checked += len(step["conditional"])
                with self.subTest(playbook=name, step=step["number"]):
                    printed = run(name, "--step", str(step["number"]), "--route", "lightweight").stdout
                    rows = [row for row in printed.split("\n") if row.startswith(label)]
                    self.assertEqual(rows, [label + ", ".join(step["conditional"])] if step["conditional"] else [])
                    for skill in step["conditional"]:
                        self.assertTrue(any(skill in names for names in full), skill)
        self.assertGreater(checked, 0)
        self.assertIn(f"{self.KEPT} none.\n{label}poteto-tdd\n", run("bug-fix", "--step", "5", "--route", "lightweight").stdout)


class OneStepUsageErrors(unittest.TestCase):
    def test_a_step_on_a_routed_playbook_needs_its_route(self):
        for name, entry in MANIFEST["playbooks"].items():
            if entry.get("tiered"):
                with self.subTest(playbook=name):
                    done = run(name, "--step", "1")
                    self.assertEqual(done.returncode, 2, done.stdout[:80])
                    self.assertEqual(done.stdout, "")
                    self.assertIn("--step needs --route", done.stderr)
        self.assertEqual(run("investigation", "--step", "1").returncode, 0)

    def test_a_route_without_a_step_is_refused(self):
        for args in (("feature", *LOW, "--route", "intensive"), ("babysit", "--route", "standard")):
            with self.subTest(playbook=args[0]):
                done = run(*args)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertEqual(done.stdout, "")
                self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
                self.assertIn("--route goes with --step", done.stderr)

    def test_flags_of_the_full_plan_are_refused_with_a_step(self):
        for extra in (("--reach", "tiny:x"), ("--reach", "low:one caller by grep"), ("--user-route", "intensive"),
                      ("--raise-to", "intensive", "--reason", "x"), ("--reason", "x"), ("--json",)):
            with self.subTest(extra=extra[0]):
                done = run("feature", "--step", "3", "--route", "standard", *extra)
                self.assertEqual(done.returncode, 2, done.stdout[:80])
                self.assertEqual(done.stdout, "")
                self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
                self.assertIn(f"Drop {extra[0]}", done.stderr)


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
        standard = {gate["id"]: gate["when"] for gate in plan("feature", *facts(reach="material:shared caller"))["gates"]}
        heavy = {gate["id"]: gate["when"] for gate in plan("feature", *facts(consequence="material:x", uncertainty="unknown"))["gates"]}
        self.assertEqual(standard["cleanup"], "before each push or published head")
        self.assertEqual(heavy["cleanup"], "before every commit or amend")
        self.assertEqual(light["preserve"], "before every commit")

    def test_the_lightweight_route_binds_only_its_listed_gates(self):
        light = [gate["id"] for gate in plan("feature", *LOW)["gates"]]
        standard = [gate["id"] for gate in plan("feature", *facts(reach="material:shared caller"))["gates"]]
        self.assertEqual(light, ["preserve", "spec-conformance", "reply-prose", "recap"])
        for gate in ("cleanup", "comment-prose", "comments", "commit-and-pr-prose", "documentation"):
            with self.subTest(gate=gate):
                self.assertNotIn(gate, light)
                self.assertIn(gate, standard)
        self.assertEqual([gate for gate in standard if gate in light], light)

    def test_recap_is_opt_in(self):
        recap = next(gate for gate in plan("feature", *LOW)["gates"] if gate["id"] == "recap")
        self.assertIn("only when the user or the repository", recap["when"])

    def test_a_gate_scoped_to_playbooks_reaches_only_those(self):
        self.assertIn("spec-conformance", [gate["id"] for gate in plan("feature", *LOW)["gates"]])
        self.assertNotIn("spec-conformance", [gate["id"] for gate in plan("refactoring", *LOW)["gates"]])

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

    def test_every_code_step_that_runs_opening_a_pr_keeps_its_commits(self):
        line = "   still commit when the push or PR is skipped"
        found = set()
        for path in sorted((MODE / "playbooks").glob("*.md")):
            numbers, number = [], None
            for row in path.read_text(encoding="utf-8").split("\n"):
                start = re.match(r"(\d+)\. ", row)
                if start:
                    number = start.group(1)
                elif row.startswith(("#", "**Reply:**")):
                    number = None
                if number and re.search(r"\bRun \*\*Opening a PR\*\*", row):
                    numbers.append(number)
            if not numbers:
                continue
            found.add(path.stem)
            entry = MANIFEST["playbooks"].get(path.stem, {})
            with self.subTest(playbook=path.stem):
                self.assertTrue(entry.get("changes_code"), "a playbook that runs Opening a PR changes code")
                args = facts(reach="material:shared caller") if entry.get("tiered") else []
                text = run(path.stem, *args).stdout.split("\n")
                for number in dict.fromkeys(numbers):
                    at = next(index for index, row in enumerate(text) if row.startswith(f"{number}. "))
                    self.assertEqual(text[at + 1], line)
        publish_without_the_step = {"babysit", "autonomous-run", "opening-a-pr"}
        code = {name for name, entry in MANIFEST["playbooks"].items() if entry.get("changes_code")}
        self.assertEqual(found, code - publish_without_the_step)
        self.assertIn(line, run("feature", *LOW).stdout, "the lightweight grouped worklist keeps the line")

    def test_a_playbook_that_changes_no_code_gets_no_commit_line(self):
        for name in ("code-review", "shipping", "investigation", "autopilot-full"):
            with self.subTest(playbook=name):
                self.assertFalse(any(step["runs_pr"] for step in plan(name)["steps"]))
                self.assertNotIn("still commit", run(name).stdout)

    def test_the_router_owns_the_commit_rule_for_a_skipped_pr(self):
        routes = (MODE / "references/routes.md").read_text(encoding="utf-8")
        self.assertIn("A skipped push or PR never skips that step's commits.", routes)


class RepositoryEndpoint(unittest.TestCase):
    PUSHED = "a pushed branch, named in the reply"
    GIT_ENV = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.bin, self.gh_config = self.root / "bin", self.root / "gh-config"
        self.bin.mkdir()
        self.gh_config.mkdir()
        (self.bin / "git").symlink_to(shutil.which("git"))

    def tool(self, name, script="exit 0"):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
        path.chmod(0o755)

    def repo(self, *urls):
        path = Path(tempfile.mkdtemp(dir=self.root))
        subprocess.run(["git", "init", "-q", str(path)], check=True, env=self.GIT_ENV)
        for index, url in enumerate(urls):
            subprocess.run(["git", "-C", str(path), "remote", "add", f"r{index}", url], check=True, env=self.GIT_ENV)
        return path

    def run_plan(self, project, *args, **env):
        env = {"PATH": str(self.bin), "HOME": str(self.root), "GH_CONFIG_DIR": str(self.gh_config), **env}
        done = subprocess.run([sys.executable, str(SCRIPT), "feature", *LOW, "--project", str(project), *args],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def endpoint(self, project, **env):
        result = json.loads(self.run_plan(project, "--json", **env).stdout)
        return result["default_endpoint"], result["scrutiny"]

    def test_no_repository_and_no_remote_take_local_commits(self):
        self.tool("gh")
        self.assertIn("git init", self.endpoint(Path(tempfile.mkdtemp(dir=self.root)))[0])
        endpoint, scrutiny = self.endpoint(self.repo())
        self.assertIn("local branch", endpoint)
        self.assertNotIn("human PR review", scrutiny)

    def test_a_local_path_remote_takes_no_pull_request(self):
        self.tool("origin")
        bare = self.root / "bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=self.GIT_ENV)
        for url in (str(bare), bare.as_uri()):
            with self.subTest(url=url):
                endpoint, scrutiny = self.endpoint(self.repo(url))
                self.assertEqual(endpoint, self.PUSHED)
                self.assertNotIn("human PR review", scrutiny)

    def test_windows_drive_paths_have_no_remote_host(self):
        remote_host = runpy.run_path(str(SCRIPT))["remote_host"]
        with patch.object(os, "path", ntpath):
            for url in (r"Z:\repos\bare.git", "Z:/repos/bare.git", "Z:bare.git"):
                with self.subTest(url=url):
                    self.assertIsNone(remote_host(url))

    def test_gh_serves_github(self):
        self.tool("gh")
        for url in ("https://github.com/o/r.git", "git@github.com:o/r.git", "ssh://git@ssh.github.com:443/o/r.git"):
            with self.subTest(url=url):
                endpoint, scrutiny = self.endpoint(self.repo(url))
                self.assertEqual(endpoint, "reviewable PR")
                self.assertIn("human PR review", scrutiny)
        self.assertEqual(self.endpoint(self.repo("https://[broken/o/r.git"))[0], self.PUSHED)

    @unittest.skipUnless(shutil.which("gh"), "requires GitHub CLI")
    def test_gh_serves_enterprise_hosts(self):
        (self.bin / "gh").symlink_to(shutil.which("gh"))
        forge = self.repo("https://forge.example.invalid/o/r.git")
        nested = self.repo("https://nested.example.invalid/o/r.git")
        endpoint, scrutiny = self.endpoint(forge)
        self.assertEqual(endpoint, self.PUSHED)
        self.assertNotIn("human PR review", scrutiny)
        self.assertEqual(self.endpoint(forge, GH_HOST="forge.example.invalid")[0], self.PUSHED)
        self.assertEqual(self.endpoint(forge, GH_HOST="forge.example.invalid", GH_ENTERPRISE_TOKEN="fixture")[0], "reviewable PR")
        (self.gh_config / "hosts.yml").write_text("forge.example.invalid:\n    user: someone\n", encoding="utf-8")
        self.assertEqual(self.endpoint(forge)[0], self.PUSHED)
        configs = ["forge.example.invalid:\n    oauth_token: fixture\n"]
        configs.extend(
            f"# hosts\n{indent}forge.example.invalid: # internal forge\n"
            f"{indent}    oauth_token: fixture\n{indent}    users:\n"
            f"{indent}        nested.example.invalid: {{}}\n" for indent in ("", "  ")
        )
        configs.append('{"forge.example.invalid": {oauth_token: fixture, users: {nested.example.invalid: {}}}}')
        for config in configs:
            with self.subTest(config=config):
                (self.gh_config / "hosts.yml").write_text(config, encoding="utf-8")
                endpoint, scrutiny = self.endpoint(forge)
                self.assertEqual(endpoint, "reviewable PR")
                self.assertIn("human PR review", scrutiny)
                self.assertEqual(self.endpoint(nested)[0], self.PUSHED)

    def test_gh_token_output_is_discarded(self):
        self.tool("gh", 'echo sentinel-token\n'
                        'for fd in 0 1 2; do [ "/dev/fd/$fd" -ef /dev/null ] || exit 1; done')
        repo = self.repo("https://forge.example.invalid/o/r.git")
        for args in ((), ("--json",)):
            with self.subTest(args=args):
                done = self.run_plan(repo, *args)
                self.assertNotIn("sentinel-token", done.stdout)
                self.assertNotIn("sentinel-token", done.stderr)
                if args:
                    self.assertEqual(json.loads(done.stdout)["default_endpoint"], "reviewable PR")
                else:
                    self.assertIn("reviewable PR", done.stdout)

    def test_gh_probes_each_enterprise_host_at_most_once(self):
        self.tool("gh", 'echo called >> "$HOME/gh-calls"\nexit 1')
        calls = self.root / "gh-calls"
        github = self.repo("https://github.com/o/a.git", "https://ssh.github.com/o/b.git")
        self.assertEqual(self.endpoint(github)[0], "reviewable PR")
        self.assertFalse(calls.exists())
        enterprise = self.repo("https://forge.example.invalid/o/a.git", "forge.example.invalid:o/b.git")
        self.assertEqual(self.endpoint(enterprise)[0], self.PUSHED)
        self.assertEqual(calls.read_text().splitlines(), ["called"])

    def test_one_remote_that_takes_a_pull_request_is_enough(self):
        self.tool("gh")
        self.assertEqual(self.endpoint(self.repo(str(self.root / "gate.git"), "https://github.com/o/r.git"))[0], "reviewable PR")

    def test_without_a_forge_cli_only_github_falls_back_to_a_built_in_tool(self):
        self.assertIn("built-in PR tool", self.endpoint(self.repo("https://github.com/o/r.git"))[0])
        self.assertEqual(self.endpoint(self.repo("https://git.example.com/o/r.git"))[0], self.PUSHED)

    def test_an_ssh_alias_counts_as_the_host_ssh_resolves(self):
        self.tool("gh")
        self.tool("ssh", 'if [ "$1" = -G ] && [ "$2" = work ]; then echo "hostname github.com"; else echo "hostname $2"; fi')
        for url in ("work:o/r.git", "ssh://git@work/o/r.git"):
            with self.subTest(url=url):
                self.assertEqual(self.endpoint(self.repo(url))[0], "reviewable PR")

    def test_a_dash_leading_host_never_reaches_ssh(self):
        self.tool("gh", "exit 1")
        self.tool("ssh", ': > "$HOME/ssh-called"')
        for url in ("ssh://-oProxyCommand=x/o/r.git", "git@-invalid:o/r.git"):
            with self.subTest(url=url):
                self.assertEqual(self.endpoint(self.repo(url))[0], self.PUSHED)
                self.assertFalse((self.root / "ssh-called").exists())

    def test_the_project_decides_under_git_environment_variables(self):
        self.tool("gh")
        other = self.repo("https://github.com/o/r.git")
        mine, plain = self.repo(), Path(tempfile.mkdtemp(dir=self.root))
        for name, value in (("GIT_DIR", other / ".git"), ("GIT_WORK_TREE", other), ("GIT_COMMON_DIR", other / ".git")):
            with self.subTest(variable=name):
                self.assertIn("local branch", self.endpoint(mine, **{name: str(value)})[0])
        self.assertIn("git init", self.endpoint(plain, GIT_DIR=str(other / ".git"))[0])

    def test_a_project_that_is_not_a_directory_is_a_usage_error(self):
        regular = self.root / "regular"
        regular.write_text("", encoding="utf-8")
        for project in ("", self.root / "missing", regular):
            with self.subTest(project=project):
                done = run("feature", *LOW, "--project", str(project))
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("--project", done.stderr)

    def test_a_repeated_project_is_refused(self):
        done = run("feature", *LOW, "--project", str(self.root), "--project", str(self.root))
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("more than once", done.stderr)

    def test_a_deleted_working_directory_still_prints_a_step(self):
        def from_deleted(*args):
            gone = Path(tempfile.mkdtemp(dir=self.root))
            return subprocess.run(["/bin/sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"', "sh", str(gone),
                                   sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

        step = from_deleted("bug-fix", "--step", "2", "--route", "standard")
        self.assertEqual(step.returncode, 0, step.stderr)
        self.assertIn("2. **Root-caused.**", step.stdout)
        self.assertEqual(from_deleted("feature", *LOW, "--project", str(self.root)).returncode, 0)
        done = from_deleted("feature", *LOW)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("--project", done.stderr)


class CodePlaybooks(unittest.TestCase):
    def test_playbooks_that_commit_or_publish_code_get_the_code_gates_and_scrutiny(self):
        for name in ("babysit", "autonomous-run", "opening-a-pr"):
            with self.subTest(playbook=name):
                result = plan(name)
                gates = [gate["id"] for gate in result["gates"]]
                for gate in ("cleanup", "comments", "commit-and-pr-prose", "documentation"):
                    self.assertIn(gate, gates)
                self.assertTrue(result["scrutiny"])
                self.assertIn("independent scrutiny: ", run(name).stdout)
                self.assertNotEqual(result["default_endpoint"], "what this playbook's Reply line names")

    def test_an_endpoint_that_names_the_reply_line_has_one(self):
        for path in sorted((MODE / "playbooks").glob("*.md")):
            args = LOW if MANIFEST["playbooks"].get(path.stem, {}).get("tiered") else []
            result = plan(path.stem, *args)
            if result["default_endpoint"] == "what this playbook's Reply line names":
                with self.subTest(playbook=path.stem):
                    self.assertTrue(result["reply"])


class Manifest(unittest.TestCase):
    def test_manifest_lists_only_playbooks_that_exist_and_need_a_flag(self):
        on_disk = {path.stem for path in (MODE / "playbooks").glob("*.md")}
        self.assertLessEqual(set(MANIFEST["playbooks"]), on_disk)
        for name, entry in MANIFEST["playbooks"].items():
            self.assertTrue(entry, f"{name} has no flag, so it needs no manifest entry")
            self.assertNotIn("file", entry)

    def test_a_playbook_without_a_manifest_entry_still_plans(self):
        self.assertNotIn("investigation", MANIFEST["playbooks"])
        self.assertEqual(plan("investigation")["route"], "standard")

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
