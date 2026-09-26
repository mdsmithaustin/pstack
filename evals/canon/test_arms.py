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

    def test_arms_rule_without_cases_from_is_refused(self):
        self.write("scratch-arms", {"rule.json": json.dumps({"source": "S2", "arms": ["current", "leaf", "leaf+trigger"]})})

        with self.assertRaisesRegex(screen.ScreenError, "must name the rule it takes cases from"):
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

    def test_patch_that_changes_nothing_is_refused(self):
        patch = "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read the leaf.\n"

        with self.assertRaisesRegex(screen.ScreenError, "arm patch changes nothing"):
            screen.apply_arm_patch(TREE, patch)

    def test_arm_mounted_when_every_line_it_adds_is(self):
        rule = screen.Rule("r", "S", None, "principle-laziness-protocol/SKILL.md", (), arm_patches=(("leaf", LEAF),))
        mounted = TREE["principle-laziness-protocol/SKILL.md"].decode()

        self.assertEqual(screen.rule_mounted(rule, mounted, TREE), False)
        self.assertEqual(screen.rule_mounted(rule, mounted + "- Restructure first when the feature would then be one small edit.\n", TREE), True)


def grade(verdict):
    return {"PASS": True, "FAIL": False}[verdict]


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
                result = {"run_number": 1, "run_base": str(run_base),
                          "assertions": [{"name": "rule-behavior", "passed": grade(verdict), "evidence": "" if verdict == "PASS" else "FAIL: wrong"}]}
                (self.out / "codex" / "stack" / case / arm / "grade.json").write_text(json.dumps({"results": [result]}))
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.compare(self.out)
        self.printed = printed.getvalue().splitlines()
        self.compared = json.loads((self.out / "compare.json").read_text())

    def test_row_shows_every_arm_verdict_in_the_rule_order(self):
        self.assertIn("codex  stack                      shop               positive  run-1  current=FAIL  leaf=PASS  leaf+trigger=PASS", self.printed)
        self.assertIn("    leaf: changed principle-laziness-protocol/SKILL.md (0 of 1 read); entry not observed; read 0 skill file(s): none", self.printed)
        self.assertIn("    leaf+trigger: changed poteto-mode/playbooks/feature.md, principle-laziness-protocol/SKILL.md (1 of 2 read); entry not observed; "
                      "read 1 skill file(s): poteto-mode/playbooks/feature.md", self.printed)
        self.assertIn("    current: entry not observed; read 0 skill file(s): none", self.printed)

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
                (out / "codex" / "pair" / "shop" / arm).mkdir(parents=True)
                result = {"run_number": 1, "run_base": str(out / "none"), "assertions": [{"name": "rule-behavior", "passed": grade(verdict), "evidence": ""}]}
                (out / "codex" / "pair" / "shop" / arm / "grade.json").write_text(json.dumps({"results": [result]}))
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                screen.compare(out)
            compared = json.loads((out / "compare.json").read_text())

        self.assertEqual(printed.getvalue().splitlines()[:4], [
            "codex  pair                       shop               positive  run-1  current=FAIL  amended=PASS  SEPARATES",
            "    current: poteto-mode/SKILL.md NOT READ; entry not observed; read 0 skill file(s): none",
            "    amended: poteto-mode/SKILL.md NOT READ; entry not observed; read 0 skill file(s): none",
            "codex  pair                       rule run-1  SEPARATES",
        ])
        self.assertEqual(compared["pairs"], [{"agent": "codex", "rule": "pair", "case": "shop", "kind": "positive", "run": 1,
                                              "target": "poteto-mode/SKILL.md", "outcome": "separates"}])
        self.assertEqual(compared["rules"], [{"agent": "codex", "rule": "pair", "run": 1, "verdict": "separates", "reasons": []}])


class ShippedArmsRuleTests(unittest.TestCase):
    def test_every_shipped_arms_rule_applies_each_arm_to_the_tracked_skills(self):
        tree = screen.tracked("skills")
        rules = [rule for rule in screen.load_rules() if not rule.paired]
        self.assertIn("bundle-prep-refactor", [rule.id for rule in rules])
        for rule in rules:
            with self.subTest(rule=rule.id):
                trees = screen.arm_trees(rule, tree)
                self.assertEqual([name for name, _ in trees], list(rule.arm_names))
                self.assertEqual(screen.changed_paths(tree, trees[1][1])[0], rule.target)


if __name__ == "__main__":
    unittest.main()
