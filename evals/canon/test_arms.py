import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("canon_screen", ROOT / "screen.py")
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)

TREE = {
    "poteto-mode/SKILL.md": b"# Poteto mode\nRead the leaf.\n",
    "poteto-mode/playbooks/feature.md": b"1. Plan.\n2. Build.\n3. Ship.\n4. Review.\n5. Merge.\n6. Watch.\n7. Close.\n",
    "principle-laziness-protocol/SKILL.md": b"- Minimize the diff.\n",
}
LEAF = """--- a/principle-laziness-protocol/SKILL.md
+++ b/principle-laziness-protocol/SKILL.md
@@ -1 +1,2 @@
 - Minimize the diff.
+- Restructure first when the feature would then be one small edit.
"""
LEAF_AND_TRIGGER = LEAF + """--- a/poteto-mode/playbooks/feature.md
+++ b/poteto-mode/playbooks/feature.md
@@ -1,2 +1,3 @@
 1. Plan.
+   Ask whether a restructure makes the feature one small edit.
 2. Build.
@@ -6,2 +7,3 @@
 6. Watch.
+   Check the restructure landed as its own commit.
 7. Close.
--- /dev/null
+++ b/poteto-mode/references/restructure.md
@@ -0,0 +1 @@
+Land the restructure before the feature.
"""
CASE = {"cases/shop/case.json": '{"kind": "positive", "domain": "d", "timeout_s": 60, "expected_behavior": ["x"]}',
        "cases/shop/prompt.md": "Add orders.\n{project}", "cases/shop/project/app.py": "x = 1\n"}


class ArmsRuleLoadTests(unittest.TestCase):
    """Arms rules against a scratch rules directory."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.rules = Path(directory.name)
        self.write("scratch-base", {"rule.json": '{"source": "S1"}', "rule.patch": "--- a/x/SKILL.md\n+++ b/x/SKILL.md\n@@ -1 +1 @@\n-a\n+b\n",
                                    "oracle.py": "CHECKS = {'shop': lambda answer, project: []}\n", **CASE})
        self.write("scratch-arms", {"rule.json": json.dumps({"cases_from": "scratch-base", "arms": ["current", "leaf", "leaf+trigger"]}),
                                    "arms/leaf.patch": LEAF, "arms/leaf+trigger.patch": LEAF_AND_TRIGGER})
        rules = mock.patch.object(screen, "RULES", self.rules)
        rules.start()
        self.addCleanup(rules.stop)

    def write(self, rule_id, files):
        for path, text in files.items():
            (self.rules / rule_id / path).parent.mkdir(parents=True, exist_ok=True)
            (self.rules / rule_id / path).write_text(text)

    def arms(self, names):
        self.write("scratch-arms", {"rule.json": json.dumps({"cases_from": "scratch-base", "arms": names})})

    def test_arms_rule_loads_its_arms_in_order_with_the_source_cases(self):
        rule = screen.load_rule("scratch-arms")

        self.assertEqual([(name, patch) for name, patch in rule.arms], [("current", None), ("leaf", LEAF), ("leaf+trigger", LEAF_AND_TRIGGER)])
        self.assertEqual((rule.paired, rule.patch, rule.target, rule.source, rule.cases_from), (False, None, "principle-laziness-protocol/SKILL.md", "S1", "scratch-base"))
        self.assertEqual(rule.skills, ("poteto-mode", "principle-laziness-protocol"))
        self.assertEqual([(case.rule, case.id) for case in rule.cases], [("scratch-arms", "shop")])
        self.assertEqual([rule.id for rule in screen.load_rules()], ["scratch-arms", "scratch-base"])

    def test_pair_rule_keeps_current_and_amended(self):
        self.assertEqual(screen.load_rule("scratch-base").arm_names, ("current", "amended"))

    def test_build_records_the_skills_each_arm_lists_by_description(self):
        added = "--- /dev/null\n+++ b/premortem/SKILL.md\n@@ -0,0 +1,4 @@\n+---\n+name: premortem\n+description: Use before a rollout.\n+---\n"
        self.write("scratch-place", {"rule.json": json.dumps({"cases_from": "scratch-base", "arms": ["current", "skill"]}), "arms/skill.patch": added})
        out = self.rules / "out"

        with contextlib.redirect_stdout(io.StringIO()) as printed:
            built = screen.build(out, [screen.load_rule("scratch-place")], "poteto-mode")["scratch-place"]

        self.assertEqual(built["arm_listed"], {"current": [], "skill": ["premortem/SKILL.md"]})
        self.assertEqual(json.loads((out / "arms" / "scratch-place" / "build.json").read_text())["arm_listed"], built["arm_listed"])
        self.assertIn("  skill: skills/premortem/SKILL.md; listed by description: premortem/SKILL.md", printed.getvalue().splitlines())

    def test_listed_arm_without_a_patch_is_refused(self):
        (self.rules / "scratch-arms" / "arms" / "leaf+trigger.patch").unlink()

        with self.assertRaisesRegex(screen.ScreenError, r"has no arms/<arm>.patch for \['leaf\+trigger'\]"):
            screen.load_rule("scratch-arms")

    def test_patch_for_an_unlisted_arm_is_refused(self):
        self.write("scratch-arms", {"arms/trigger.patch": LEAF})

        with self.assertRaisesRegex(screen.ScreenError, r"does not list after current: \['trigger'\]"):
            screen.load_rule("scratch-arms")

    def test_arms_that_do_not_start_with_current_are_refused(self):
        self.arms(["leaf", "current", "leaf+trigger"])

        with self.assertRaisesRegex(screen.ScreenError, "must be a list that starts with current"):
            screen.load_rule("scratch-arms")

    def test_bad_arm_name_is_refused(self):
        self.arms(["current", "Leaf", "leaf+trigger"])

        with self.assertRaisesRegex(screen.ScreenError, "distinct name matching"):
            screen.load_rule("scratch-arms")

    def test_arms_rule_with_a_rule_patch_is_refused(self):
        self.write("scratch-arms", {"rule.patch": LEAF})

        with self.assertRaisesRegex(screen.ScreenError, "lists arms, so it must not have rule.patch"):
            screen.load_rule("scratch-arms")

    def test_arms_rule_without_cases_from_needs_its_own_cases(self):
        self.write("scratch-arms", {"rule.json": json.dumps({"source": "S2", "arms": ["current", "leaf", "leaf+trigger"]})})

        with self.assertRaisesRegex(screen.ScreenError, "rule scratch-arms has no oracle.py"):
            screen.load_rule("scratch-arms")

    def test_stub_rule_that_owns_its_cases_grades_them_with_its_own_oracle(self):
        self.write("scratch-own", {"rule.json": json.dumps({"source": "S3", "arms": ["current", "stub"]}),
                                   "oracle.py": "CHECKS = {'shop': lambda answer, project: []}\n", **CASE})

        rule = screen.load_rule("scratch-own")

        self.assertEqual((rule.arm_names, rule.case_rule, rule.source), (("current", "stub"), "scratch-own", "S3"))
        self.assertEqual([(case.rule, case.id) for case in rule.cases], [("scratch-own", "shop")])

    def test_stub_arm_needs_no_patch_and_the_rule_needs_no_arms_directory(self):
        self.write("scratch-stub", {"rule.json": json.dumps({"cases_from": "scratch-base", "arms": ["current", "stub"]})})

        rule = screen.load_rule("scratch-stub")

        self.assertEqual((rule.arms, rule.target, rule.skills), ((("current", None), ("stub", None)), "poteto-mode/SKILL.md", ("poteto-mode",)))
        self.assertIn("scratch-stub", [rule.id for rule in screen.load_rules()])

    def test_patch_for_the_stub_arm_is_refused(self):
        self.arms(["current", "leaf", "leaf+trigger", "stub"])
        self.write("scratch-arms", {"arms/stub.patch": LEAF})

        with self.assertRaisesRegex(screen.ScreenError, "has arms/stub.patch, but the stub arm is built from current"):
            screen.load_rule("scratch-arms")

    def test_stub_arm_needs_no_patch_and_the_rule_needs_no_arms_directory(self):
        self.write("scratch-stub", {"rule.json": json.dumps({"cases_from": "scratch-base", "arms": ["current", "stub"]})})

        rule = screen.load_rule("scratch-stub")

        self.assertEqual((rule.arms, rule.target, rule.skills), ((("current", None), ("stub", None)), "poteto-mode/SKILL.md", ("poteto-mode",)))
        self.assertIn("scratch-stub", [rule.id for rule in screen.load_rules()])

    def test_patch_for_the_stub_arm_is_refused(self):
        self.arms(["current", "leaf", "leaf+trigger", "stub"])
        self.write("scratch-arms", {"arms/stub.patch": LEAF})

        with self.assertRaisesRegex(screen.ScreenError, "has arms/stub.patch, but the stub arm is built from current"):
            screen.load_rule("scratch-arms")

    def test_arms_rule_whose_source_is_a_variant_is_refused(self):
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-base"}', "rule.patch": LEAF})
        self.write("scratch-arms", {"rule.json": json.dumps({"cases_from": "scratch-variant", "arms": ["current", "leaf", "leaf+trigger"]})})

        with self.assertRaisesRegex(screen.ScreenError, "which takes its own from scratch-base"):
            screen.load_rule("scratch-arms")


class ArmPatchTests(unittest.TestCase):
    def test_patch_across_files_and_hunks_applies_and_adds_a_new_file(self):
        applied = screen.apply_arm_patch(TREE, LEAF_AND_TRIGGER)

        self.assertEqual(applied, {
            "poteto-mode/SKILL.md": b"# Poteto mode\nRead the leaf.\n",
            "poteto-mode/playbooks/feature.md": b"1. Plan.\n   Ask whether a restructure makes the feature one small edit.\n2. Build.\n3. Ship.\n4. Review.\n5. Merge.\n"
                                                b"6. Watch.\n   Check the restructure landed as its own commit.\n7. Close.\n",
            "poteto-mode/references/restructure.md": b"Land the restructure before the feature.\n",
            "principle-laziness-protocol/SKILL.md": b"- Minimize the diff.\n- Restructure first when the feature would then be one small edit.\n",
        })
        self.assertEqual(screen.changed_paths(TREE, applied),
                         ["poteto-mode/playbooks/feature.md", "poteto-mode/references/restructure.md", "principle-laziness-protocol/SKILL.md"])

    def test_paths_under_skills_are_read_relative_to_skills(self):
        patch = "--- a/skills/poteto-mode/SKILL.md\n+++ b/skills/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read the leaf first.\n"

        applied = screen.apply_arm_patch(TREE, patch)

        self.assertEqual(screen.patch_paths(patch), (2, ["poteto-mode/SKILL.md"]))
        self.assertEqual(applied["poteto-mode/SKILL.md"], b"# Poteto mode\nRead the leaf first.\n")

    def test_patch_may_delete_a_file(self):
        patch = "--- a/principle-laziness-protocol/SKILL.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-- Minimize the diff.\n"

        applied = screen.apply_arm_patch(TREE, patch)

        self.assertEqual(sorted(applied), ["poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md"])

    def test_patch_that_does_not_apply_is_refused(self):
        patch = "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the index.\n+Read the leaf first.\n"

        with self.assertRaisesRegex(screen.ScreenError, "arm patch does not apply to skills/: .*poteto-mode/SKILL.md"):
            screen.apply_arm_patch(TREE, patch)

    def test_an_added_ungated_skill_is_listed_and_a_gated_or_edited_one_is_not(self):
        def adds(path, text):
            return "--- /dev/null\n+++ b/" + path + "\n@@ -0,0 +1," + str(text.count("\n")) + " @@\n" + "".join("+" + line + "\n" for line in text.splitlines())

        open_skill = adds("premortem/SKILL.md", "---\nname: premortem\ndescription: Use before a rollout.\n---\n# Premortem\n")
        gated = adds("gated/SKILL.md", "---\nname: gated\ndescription: Style.\ndisable-model-invocation: true\n---\n# Gated\n")
        implicit_off = adds("quiet/SKILL.md", "---\nname: quiet\n---\n# Quiet\n") + adds("quiet/agents/openai.yaml", "policy:\n  allow_implicit_invocation: false\n")
        implicit_on = (adds("loud/SKILL.md", "---\nname: loud\ndisable-model-invocation: false\n---\n# Loud\n")
                       + adds("loud/agents/openai.yaml", "policy:\n  allow_implicit_invocation: true\n"))
        fronted = {"poteto-mode/SKILL.md": b"---\nname: poteto-mode\n---\n# P\n", "principle-laziness-protocol/SKILL.md": b"---\nname: lazy\n---\n# L\n"}
        trees = [("current", TREE), ("skill", screen.apply_arm_patch(TREE, open_skill)), ("gated", screen.apply_arm_patch(TREE, gated)),
                 ("quiet", screen.apply_arm_patch(TREE, implicit_off)), ("loud", screen.apply_arm_patch(TREE, implicit_on)),
                 ("leaf", screen.apply_arm_patch(TREE, LEAF)), ("both", screen.apply_arm_patch(TREE, open_skill + LEAF)), ("stub", screen.stub_tree(fronted))]

        self.assertEqual(screen.arm_listed(TREE, trees), {"current": [], "skill": ["premortem/SKILL.md"], "gated": [], "quiet": [], "loud": ["loud/SKILL.md"],
                                                          "leaf": [], "both": ["premortem/SKILL.md"], "stub": []})

    def test_auto_invocable_uses_the_setup_policy_contract_for_each_skill(self):
        """Codex policy gating excludes a skill from every-run description exposure.
        These policy examples reject false positives outside policy and omitted inline gating.
        """
        policies = [
            (b"policy:\n  allow_implicit_invocation: false\n", False),
            (b'policy: {allow_implicit_invocation: "false"}\n', False),
            (b"policy:\n  allow_implicit_invocation: 'false'\n", False),
            (b"interface:\n  allow_implicit_invocation: false\n", True),
            (b"policy:\n  allow_implicit_invocation: true\n", True),
            (b"", True),
        ]
        for name in ("arena", "companion"):
            for policy, expected in policies:
                with self.subTest(name=name, policy=policy):
                    path = f"{name}/SKILL.md"
                    tree = {path: b"---\nname: skill\n---\n", f"{name}/agents/openai.yaml": policy}
                    self.assertEqual(screen.auto_invocable(tree, path), expected)

    def test_patch_that_changes_nothing_is_refused(self):
        patch = "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read the leaf.\n"

        with self.assertRaisesRegex(screen.ScreenError, "arm patch changes nothing"):
            screen.apply_arm_patch(TREE, patch)

    def test_stub_keeps_each_skill_md_frontmatter_and_openai_yaml_and_drops_everything_else(self):
        tree = {
            "poteto-mode/SKILL.md": b"---\nname: poteto-mode\ndescription: Style.\n---\n\n# Poteto mode\nRead the leaf.\n",
            "poteto-mode/agents/openai.yaml": b"policy:\n  allow_implicit_invocation: false\n",
            "poteto-mode/playbooks/feature.md": b"1. Plan.\n",
            "poteto-mode/references/agents/openai.yaml": b"policy:\n  allow_implicit_invocation: false\n",
            "why/SKILL.md": b"---\nname: why\ndescription: \"Rationale: ---\"\n---",
        }

        self.assertEqual(screen.stub_tree(tree), {
            "poteto-mode/SKILL.md": b"---\nname: poteto-mode\ndescription: Style.\n---\n",
            "poteto-mode/agents/openai.yaml": b"policy:\n  allow_implicit_invocation: false\n",
            "why/SKILL.md": b"---\nname: why\ndescription: \"Rationale: ---\"\n---",
        })

    def test_stub_refuses_a_skill_md_without_frontmatter(self):
        with self.assertRaisesRegex(screen.ScreenError, "skills/poteto-mode/SKILL.md has no frontmatter"):
            screen.stub_tree(TREE)

    def test_arm_mounted_when_every_line_it_adds_is(self):
        rule = screen.Rule("r", "S", None, "principle-laziness-protocol/SKILL.md", (), arm_patches=(("leaf", LEAF),))
        mounted = TREE["principle-laziness-protocol/SKILL.md"].decode()

        self.assertEqual(screen.rule_mounted(rule, mounted, TREE), False)
        self.assertEqual(screen.rule_mounted(rule, mounted + "- Restructure first when the feature would then be one small edit.\n", TREE), True)


    def test_pair_rule_that_cuts_text_is_mounted_only_where_the_cut_text_is_gone(self):
        cut = "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read.\n"
        rule = screen.Rule("r", "S", cut, "poteto-mode/SKILL.md", ())

        self.assertEqual(screen.rule_mounted(rule, TREE["poteto-mode/SKILL.md"].decode(), TREE), False)
        self.assertEqual(screen.rule_mounted(rule, "# Poteto mode\nRead.\n", TREE), True)

    def test_pair_rule_that_adds_text_is_mounted_where_the_new_text_is(self):
        add = "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read the leaf twice.\n"
        rule = screen.Rule("r", "S", add, "poteto-mode/SKILL.md", ())

        self.assertEqual(screen.rule_mounted(rule, TREE["poteto-mode/SKILL.md"].decode(), TREE), False)
        self.assertEqual(screen.rule_mounted(rule, "# Poteto mode\nRead the leaf twice.\n", TREE), True)

def grade(verdict):
    return {"PASS": True, "FAIL": False}[verdict]


def codex_injected(run_base):
    """Write the rollout the sbx runner harvests for a Codex run that got the
    $poteto-mode injection."""
    runs = next(parent for parent in run_base.parents if parent.name == "runs")
    rollout = runs.parent / "harvest" / run_base.relative_to(runs) / "transcripts" / "codex" / "sessions" / "rollout-a.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "<skill>\n<name>poteto-mode</name>\n"}]}}) + "\n")


def claude_injected(run_base):
    """Write the trace init listing and the session transcript the sbx runner
    harvests for a Claude run whose /poteto-mode token expanded."""
    runs = next(parent for parent in run_base.parents if parent.name == "runs")
    (run_base / "trace.jsonl").write_text(json.dumps({"type": "system", "subtype": "init", "skills": ["poteto-mode"], "slash_commands": ["poteto-mode"]}) + "\n")
    transcript = runs.parent / "harvest" / run_base.relative_to(runs) / "transcripts" / "claude" / "-ws" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "<command-name>/poteto-mode</command-name>"}}) + "\n")


class ArmsCompareTests(unittest.TestCase):
    """compare over synthetic grades for a rule with arms current, leaf, and leaf+trigger."""

    CHANGES = {"current": [], "leaf": ["principle-laziness-protocol/SKILL.md"],
               "leaf+trigger": ["poteto-mode/playbooks/feature.md", "principle-laziness-protocol/SKILL.md"]}
    RUNS = {
        "shop": {"current": ("FAIL", []), "leaf": ("PASS", []), "leaf+trigger": ("PASS", ["poteto-mode/playbooks/feature.md"])},
        "quiet": {"current": ("PASS", []), "leaf": ("FAIL", ["principle-laziness-protocol/SKILL.md"]),
                  "leaf+trigger": ("PASS", ["poteto-mode/playbooks/feature.md"])},
    }

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        trees = {"current": TREE, "leaf": screen.apply_arm_patch(TREE, LEAF), "leaf+trigger": screen.apply_arm_patch(TREE, LEAF_AND_TRIGGER)}
        build = {"entry": "poteto-mode", "tree_dir": "pstack", "target": "principle-laziness-protocol/SKILL.md", "patch_kind": "arms",
                 "arm_changes": self.CHANGES, "arms": ["current", "leaf", "leaf+trigger"],
                 "cases": {"shop": {"kind": "positive", "timeout_s": 900}, "quiet": {"kind": "near-miss", "timeout_s": 900}}}
        (self.out / "arms" / "stack").mkdir(parents=True)
        (self.out / "arms" / "stack" / "build.json").write_text(json.dumps(build))
        for case, arms in self.RUNS.items():
            for arm, (verdict, read) in arms.items():
                for path, data in trees[arm].items():
                    (self.out / "arms" / "stack" / case / arm / "pstack" / path).parent.mkdir(parents=True, exist_ok=True)
                    (self.out / "arms" / "stack" / case / arm / "pstack" / path).write_bytes(data)
                run_base = self.out / "codex" / "stack" / case / arm / "runs" / case / "with_skill"
                run_base.mkdir(parents=True)
                events = [{"type": "command", "status": "completed", "input_summary": f"sed -n 1,400p .agents/skills/{path}"} for path in read]
                (run_base / "events.json").write_text(json.dumps({"events": events}))
                codex_injected(run_base)
                result = {"run_number": 1, "run_base": str(run_base),
                          "assertions": [{"name": "rule-behavior", "passed": grade(verdict), "evidence": "" if verdict == "PASS" else "FAIL: wrong"}]}
                (self.out / "codex" / "stack" / case / arm / "grade.json").write_text(json.dumps({"results": [result]}))
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.compare(self.out)
        self.printed = printed.getvalue().splitlines()
        self.compared = json.loads((self.out / "compare.json").read_text())

    def test_row_shows_every_arm_verdict_in_the_rule_order(self):
        self.assertIn("codex  stack                      shop               positive  run-1  current=FAIL  leaf=PASS  leaf+trigger=PASS", self.printed)
        self.assertIn("    leaf: changed principle-laziness-protocol/SKILL.md (0 of 1 read); entry injected; read 0 skill file(s): none", self.printed)
        self.assertIn("    leaf+trigger: changed poteto-mode/playbooks/feature.md, principle-laziness-protocol/SKILL.md (1 of 2 read); entry injected; "
                      "read 1 skill file(s): poteto-mode/playbooks/feature.md", self.printed)
        self.assertIn("    current: entry injected; read 0 skill file(s): none", self.printed)

    def test_each_arm_against_current_then_each_later_arm_against_each_earlier_one(self):
        pairs = [(pair["case"], pair["treatment"], pair["baseline"], pair["target"], pair["outcome"]) for pair in self.compared["pairs"]]

        self.assertEqual(pairs, [
            ("quiet", "leaf", "current", ["principle-laziness-protocol/SKILL.md"], "reverses"),
            ("quiet", "leaf+trigger", "current", ["poteto-mode/playbooks/feature.md", "principle-laziness-protocol/SKILL.md"], "tie-pass"),
            ("quiet", "leaf+trigger", "leaf", ["poteto-mode/playbooks/feature.md"], "separates"),
            ("shop", "leaf", "current", ["principle-laziness-protocol/SKILL.md"], "unexposed"),
            ("shop", "leaf+trigger", "current", ["poteto-mode/playbooks/feature.md", "principle-laziness-protocol/SKILL.md"], "separates"),
            ("shop", "leaf+trigger", "leaf", ["poteto-mode/playbooks/feature.md"], "tie-pass"),
        ])
        self.assertEqual(self.printed[self.printed.index("    leaf+trigger vs current: SEPARATES") - 1], "    leaf vs current: UNEXPOSED")

    def test_one_rule_verdict_per_arm_against_current(self):
        rules = [(row["arm"], row["verdict"], row["reasons"]) for row in self.compared["rules"]]

        self.assertEqual(rules, [("leaf", "not-separated", ["quiet reverses", "shop unexposed"]), ("leaf+trigger", "separates", [])])
        self.assertIn("codex  stack                      rule leaf+trigger vs current run-1  SEPARATES", self.printed)

    def test_each_arm_counts_the_runs_its_changed_text_reached(self):
        self.assertEqual(self.compared["arms"], [
            {"agent": "codex", "rule": "stack", "arm": "leaf", "changed_text_reached": 1, "runs": 2, "listed": []},
            {"agent": "codex", "rule": "stack", "arm": "leaf+trigger", "changed_text_reached": 2, "runs": 2, "listed": []},
        ])
        self.assertIn("codex  stack                      arm leaf: changed text reached 1/2 run(s)", self.printed)
        self.assertIn("codex  stack                      arm leaf+trigger: changed text reached 2/2 run(s)", self.printed)


class ListedSkillCompareTests(unittest.TestCase):
    """compare for a rule whose skill arm adds an auto-invocable skill that no run loaded."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        skill = {**TREE, "premortem/SKILL.md": b"---\nname: premortem\ndescription: Use before a rollout.\n---\n# Premortem\n"}
        build = {"entry": "poteto-mode", "tree_dir": "pstack", "target": "premortem/SKILL.md", "patch_kind": "arms",
                 "arm_changes": {"current": [], "skill": ["premortem/SKILL.md"]}, "arm_listed": {"current": [], "skill": ["premortem/SKILL.md"]},
                 "arms": ["current", "skill"], "cases": {"rollout": {"kind": "positive", "timeout_s": 900}}}
        (self.out / "arms" / "place").mkdir(parents=True)
        (self.out / "arms" / "place" / "build.json").write_text(json.dumps(build))
        for arm, tree, read in (("current", TREE, []), ("skill", skill, [])):
            for path, data in tree.items():
                (self.out / "arms" / "place" / "rollout" / arm / "pstack" / path).parent.mkdir(parents=True, exist_ok=True)
                (self.out / "arms" / "place" / "rollout" / arm / "pstack" / path).write_bytes(data)
            run_base = self.out / "claude" / "place" / "rollout" / arm / "runs" / "rollout" / "with_skill"
            run_base.mkdir(parents=True)
            claude_injected(run_base)
            (run_base / "events.json").write_text(json.dumps({"events": read}))
            result = {"run_number": 1, "run_base": str(run_base), "assertions": [{"name": "rule-behavior", "passed": False, "evidence": "FAIL: wrong"}]}
            (self.out / "claude" / "place" / "rollout" / arm / "grade.json").write_text(json.dumps({"results": [result]}))
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.compare(self.out)
        self.printed = printed.getvalue().splitlines()
        self.compared = json.loads((self.out / "compare.json").read_text())

    def test_an_unloaded_listed_skill_is_a_tie_fail_not_unexposed(self):
        self.assertEqual([(pair["treatment"], pair["outcome"]) for pair in self.compared["pairs"]], [("skill", "tie-fail")])
        self.assertEqual(self.compared["arms"], [{"agent": "claude", "rule": "place", "arm": "skill", "changed_text_reached": 0, "runs": 1, "listed": ["premortem/SKILL.md"]}])
        self.assertIn("claude place                      arm skill: changed text reached 0/1 run(s); listed by description: premortem/SKILL.md", self.printed)


class StubCompareTests(unittest.TestCase):
    """compare over synthetic grades for a rule with arms current and stub under the skill entry."""

    TREE = {
        "poteto-mode/SKILL.md": b"---\nname: poteto-mode\ndescription: Style.\n---\n# Poteto mode\nRead the leaf.\n",
        "poteto-mode/playbooks/feature.md": b"1. Plan.\n",
    }
    RUNS = {
        "shop": {"current": ("PASS", ["poteto-mode/playbooks/feature.md"]), "stub": ("FAIL", ["poteto-mode/SKILL.md"])},
        "quiet": {"current": ("PASS", []), "stub": ("PASS", ["poteto-mode/SKILL.md"])},
    }

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        trees = {"current": self.TREE, "stub": screen.stub_tree(self.TREE)}
        build = {"entry": "skill", "tree_dir": "skills", "target": "poteto-mode/SKILL.md", "patch_kind": "arms",
                 "arm_changes": {"current": [], "stub": sorted(self.TREE)}, "arms": ["current", "stub"],
                 "cases": {"shop": {"kind": "positive", "timeout_s": 900}, "quiet": {"kind": "near-miss", "timeout_s": 900}}}
        (self.out / "arms" / "steer").mkdir(parents=True)
        (self.out / "arms" / "steer" / "build.json").write_text(json.dumps(build))
        for case, arms in self.RUNS.items():
            for arm, (verdict, read) in arms.items():
                for path, data in trees[arm].items():
                    (self.out / "arms" / "steer" / case / arm / "skills" / path).parent.mkdir(parents=True, exist_ok=True)
                    (self.out / "arms" / "steer" / case / arm / "skills" / path).write_bytes(data)
                run_base = self.out / "codex" / "steer" / case / arm / "runs" / case / "with_skill"
                run_base.mkdir(parents=True)
                events = [{"type": "file_read", "status": "completed", "input_summary": f"skills/{path}"} for path in read]
                (run_base / "events.json").write_text(json.dumps({"events": events}))
                result = {"run_number": 1, "run_base": str(run_base),
                          "assertions": [{"name": "rule-behavior", "passed": grade(verdict), "evidence": "" if verdict == "PASS" else "FAIL: wrong"}]}
                (self.out / "codex" / "steer" / case / arm / "grade.json").write_text(json.dumps({"results": [result]}))
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.compare(self.out)
        self.printed = printed.getvalue().splitlines()
        self.compared = json.loads((self.out / "compare.json").read_text())

    def test_stub_is_the_baseline_and_exposure_asks_whether_the_guided_arm_read_guidance(self):
        pairs = [(pair["case"], pair["treatment"], pair["baseline"], pair["target"], pair["outcome"]) for pair in self.compared["pairs"]]

        self.assertEqual(pairs, [
            ("quiet", "current", "stub", ["poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md"], "unexposed"),
            ("shop", "current", "stub", ["poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md"], "separates"),
        ])
        self.assertIn("    current vs stub: SEPARATES", self.printed)
        self.assertIn("    stub: changed 1 SKILL.md cut to frontmatter, 1 other file(s) dropped (1 of 2 read); entry read; "
                      "read 1 skill file(s): poteto-mode/SKILL.md", self.printed)

    def test_rule_verdict_names_current_against_the_stub(self):
        self.assertEqual([(row["arm"], row["verdict"], row["reasons"]) for row in self.compared["rules"]], [("stub", "not-separated", ["quiet unexposed"])])
        self.assertIn("codex  steer                      rule current vs stub run-1  NOT-SEPARATED  (quiet unexposed)", self.printed)

    def test_under_the_poteto_mode_entry_the_injected_index_exposes_the_guided_arm(self):
        """The stub keeps poteto-mode's frontmatter, so its entry registers and
        injects too, and the baseline's evidence is as real as the guided arm's."""
        baseline = {"verdict": "PASS", "exposure": {"read": [], "entry": "injected"}}
        unseen = {"verdict": "PASS", "exposure": {"read": [], "entry": "not observed"}}

        self.assertEqual(screen.classify(baseline, dict(baseline), sorted(self.TREE), "poteto-mode"), "tie-pass")
        self.assertEqual(screen.classify(unseen, dict(unseen), sorted(self.TREE), "poteto-mode"), "unexposed")
        self.assertEqual(screen.classify(unseen, dict(unseen), sorted(self.TREE), "skill"), "unexposed")


class PairCompareTests(unittest.TestCase):
    def test_pair_rule_prints_one_outcome_per_case_and_no_arm_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            build = {"entry": "poteto-mode", "tree_dir": "pstack", "target": "poteto-mode/SKILL.md", "patch_kind": "insert",
                     "removed": "", "inserted": " x", "arms": ["current", "amended"], "cases": {"shop": {"kind": "positive", "timeout_s": 900}}}
            (out / "arms" / "pair").mkdir(parents=True)
            (out / "arms" / "pair" / "build.json").write_text(json.dumps(build))
            for arm, verdict in (("current", "FAIL"), ("amended", "PASS")):
                (out / "arms" / "pair" / "shop" / arm / "pstack").mkdir(parents=True)
                run_base = out / "codex" / "pair" / "shop" / arm / "runs" / "shop" / "with_skill"
                run_base.mkdir(parents=True)
                codex_injected(run_base)
                result = {"run_number": 1, "run_base": str(run_base), "assertions": [{"name": "rule-behavior", "passed": grade(verdict), "evidence": ""}]}
                (out / "codex" / "pair" / "shop" / arm / "grade.json").write_text(json.dumps({"results": [result]}))
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                screen.compare(out)
            compared = json.loads((out / "compare.json").read_text())

        self.assertEqual(printed.getvalue().splitlines()[:4], [
            "codex  pair                       shop               positive  run-1  current=FAIL  amended=PASS  SEPARATES",
            "    current: poteto-mode/SKILL.md NOT READ; entry injected; read 0 skill file(s): none",
            "    amended: poteto-mode/SKILL.md NOT READ; entry injected; read 0 skill file(s): none",
            "codex  pair                       rule run-1  SEPARATES",
        ])
        self.assertEqual(compared["pairs"], [{"agent": "codex", "rule": "pair", "case": "shop", "kind": "positive", "run": 1,
                                              "target": "poteto-mode/SKILL.md", "outcome": "separates"}])
        self.assertEqual(compared["rules"], [{"agent": "codex", "rule": "pair", "run": 1, "verdict": "separates", "reasons": []}])


class ShippedArmsRuleTests(unittest.TestCase):
    def test_every_shipped_arms_rule_applies_each_arm_to_the_tracked_skills(self):
        rules = [rule for rule in screen.load_rules() if not rule.paired]
        self.assertIn("bundle-prep-refactor", [rule.id for rule in rules])
        for rule in rules:
            with self.subTest(rule=rule.id):
                tree = screen.rule_tree(rule)
                trees = screen.arm_trees(rule, tree)
                self.assertEqual([name for name, _ in trees], list(rule.arm_names))
                self.assertIn(rule.target, screen.changed_paths(tree, trees[1][1]))


if __name__ == "__main__":
    unittest.main()
