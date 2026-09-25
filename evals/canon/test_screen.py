import contextlib
import dataclasses
import importlib.util
import io
import json
import os
import subprocess
import sys
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
    "poteto-mode/playbooks/feature.md": b"1. Plan.\n2. Build.\n3. Ship.\n",
    "principle-laziness-protocol/SKILL.md": b"- Minimize the diff.\n",
}


class OneChangeAcrossTreeTests(unittest.TestCase):
    def test_one_insertion_in_one_file_of_the_tree_is_the_rule(self):
        amended = {**TREE, "poteto-mode/playbooks/feature.md": b"1. Plan. Split first.\n2. Build.\n3. Ship.\n"}

        change = screen.single_change(TREE, amended)

        self.assertEqual(change, screen.Change("poteto-mode/playbooks/feature.md", "", " Split first."))
        self.assertEqual(change.kind, "insert")

    def test_edits_in_two_files_are_refused(self):
        amended = {
            **TREE,
            "poteto-mode/SKILL.md": b"# Poteto mode\nRead the leaf first.\n",
            "principle-laziness-protocol/SKILL.md": b"- Minimize the diff. List callers.\n",
        }

        with self.assertRaisesRegex(screen.ScreenError, "exactly one file"):
            screen.single_change(TREE, amended)

    def test_two_separate_insertions_in_one_file_are_refused(self):
        amended = {**TREE, "poteto-mode/playbooks/feature.md": b"1. Plan first.\n2. Build.\n3. Ship it.\n"}

        with self.assertRaisesRegex(screen.ScreenError, "beyond one contiguous change"):
            screen.single_change(TREE, amended)

    def test_a_replaced_word_is_one_replacement(self):
        amended = {**TREE, "principle-laziness-protocol/SKILL.md": b"- Maximize the diff.\n"}

        change = screen.single_change(TREE, amended)

        self.assertEqual(change, screen.Change("principle-laziness-protocol/SKILL.md", "in", "ax"))
        self.assertEqual(change.kind, "replace")

    def test_every_shipped_rule_is_one_change_across_all_tracked_skills(self):
        tree = screen.tracked("skills")
        for rule in (rule for rule in screen.load_rules() if rule.paired):
            with self.subTest(rule=rule.id):
                change = screen.rule_change(rule, tree)
                self.assertEqual(change.target, rule.target)
                self.assertTrue(change.inserted.strip())


FEATURE_HEAD = "--- a/poteto-mode/playbooks/feature.md\n+++ b/poteto-mode/playbooks/feature.md\n"


class OneHunkPatchTests(unittest.TestCase):
    def test_one_hunk_replacing_a_line_applies(self):
        patch = FEATURE_HEAD + "@@ -1,3 +1,4 @@\n 1. Plan.\n-2. Build.\n+2. Split the module.\n+2b. Add the flag.\n 3. Ship.\n"

        amended = screen.apply_patch(TREE, patch)

        self.assertEqual(amended["poteto-mode/playbooks/feature.md"], b"1. Plan.\n2. Split the module.\n2b. Add the flag.\n3. Ship.\n")
        self.assertEqual(
            screen.single_change(TREE, amended),
            screen.Change("poteto-mode/playbooks/feature.md", "Build", "Split the module.\n2b. Add the flag"),
        )

    def test_two_hunks_are_refused(self):
        patch = FEATURE_HEAD + "@@ -1 +1 @@\n-1. Plan.\n+1. Plan first.\n@@ -3 +3 @@\n-3. Ship.\n+3. Ship it.\n"

        with self.assertRaisesRegex(screen.ScreenError, "exactly one hunk, it has 2"):
            screen.apply_patch(TREE, patch)

    def test_edits_split_by_an_unchanged_line_in_one_hunk_are_refused(self):
        patch = FEATURE_HEAD + "@@ -1,3 +1,3 @@\n-1. Plan.\n+1. Plan first.\n 2. Build.\n-3. Ship.\n+3. Ship it.\n"

        with self.assertRaisesRegex(screen.ScreenError, "one contiguous change"):
            screen.apply_patch(TREE, patch)

    def test_blank_context_line_without_its_space_is_still_parsed(self):
        tree = {**TREE, "poteto-mode/playbooks/feature.md": b"1. Plan.\n\n2. Build.\n"}
        stripped = FEATURE_HEAD + "@@ -1,3 +1,4 @@\n 1. Plan.\n+1b. Split.\n\n-2. Build.\n+2. Build it.\n"

        with self.assertRaisesRegex(screen.ScreenError, "one contiguous change"):
            screen.apply_patch(tree, stripped)

    def test_trailing_blank_line_after_the_hunk_is_ignored(self):
        patch = FEATURE_HEAD + "@@ -1,2 +1,3 @@\n 1. Plan.\n+1b. Split.\n 2. Build.\n\n"

        amended = screen.apply_patch(TREE, patch)

        self.assertEqual(amended["poteto-mode/playbooks/feature.md"], b"1. Plan.\n1b. Split.\n2. Build.\n3. Ship.\n")

    def test_hunk_shorter_than_its_header_is_refused(self):
        patch = FEATURE_HEAD + "@@ -1,4 +1,5 @@\n 1. Plan.\n+1b. Split.\n 2. Build.\n"

        with self.assertRaisesRegex(screen.ScreenError, "hunk ends early"):
            screen.apply_patch(TREE, patch)

    def test_two_files_are_refused(self):
        patch = (
            FEATURE_HEAD + "@@ -1 +1 @@\n-1. Plan.\n+1. Plan first.\n"
            "--- a/poteto-mode/SKILL.md\n+++ b/poteto-mode/SKILL.md\n@@ -2 +2 @@\n-Read the leaf.\n+Read it.\n"
        )

        with self.assertRaisesRegex(screen.ScreenError, "exactly one file, it names 2"):
            screen.apply_patch(TREE, patch)


def run_row(verdict, read, invoked=False):
    return {"verdict": verdict, "exposure": {"read": read, "entry_invoked": invoked}}


class PairOutcomeTests(unittest.TestCase):
    target = "principle-laziness-protocol/SKILL.md"

    def test_amended_arm_that_never_read_the_patched_file_is_unexposed_not_a_tie(self):
        outcome = screen.classify(run_row("PASS", [self.target]), run_row("PASS", ["poteto-mode/SKILL.md"], True), self.target)

        self.assertEqual(outcome, "unexposed")

    def test_unexposed_wins_over_an_apparent_separation(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), self.target)

        self.assertEqual(outcome, "unexposed")

    def test_exposed_pairs_are_named_by_their_verdicts(self):
        cases = {("FAIL", "PASS"): "separates", ("PASS", "PASS"): "tie-pass", ("FAIL", "FAIL"): "tie-fail", ("PASS", "FAIL"): "reverses"}
        for (current, amended), expected in cases.items():
            with self.subTest(current=current, amended=amended):
                self.assertEqual(screen.classify(run_row(current, []), run_row(amended, [self.target]), self.target), expected)

    def test_patched_entry_file_counts_as_read_when_the_invocation_loaded_it(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", [], True), "poteto-mode/SKILL.md")

        self.assertEqual(outcome, "separates")

    def test_patched_index_counts_as_exposed_under_the_poteto_mode_entry(self):
        """Codex never shows the $poteto-mode injection and Claude's -p stream
        never shows the /poteto-mode expansion, so the entry is the evidence."""
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), "poteto-mode/SKILL.md", "poteto-mode")

        self.assertEqual(outcome, "separates")

    def test_patched_index_is_unexposed_under_the_single_skill_entry_when_unread(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), "poteto-mode/SKILL.md", "skill")

        self.assertEqual(outcome, "unexposed")

    def test_the_entry_exposes_only_the_index_not_a_leaf(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), self.target, "poteto-mode")

        self.assertEqual(outcome, "unexposed")

    def test_ungradable_arm_is_invalid(self):
        outcome = screen.classify(run_row("PASS", [self.target]), run_row("INVALID", [self.target]), self.target)

        self.assertEqual(outcome, "invalid")


class RuleVerdictTests(unittest.TestCase):
    def test_rule_separates_when_positives_separate_and_near_miss_holds(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "tie-pass")]

        self.assertEqual(screen.rule_verdict(outcomes), ("separates", []))

    def test_near_miss_that_reverses_blocks_the_rule(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "reverses")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["bdd reverses"]))

    def test_every_positive_case_must_separate(self):
        outcomes = [("plain", "positive", "separates"), ("other", "positive", "tie-pass"), ("bdd", "near-miss", "tie-fail")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["other tie-pass"]))

    def test_ungraded_near_miss_cannot_show_the_rule_held(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "invalid")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["bdd invalid"]))


class NearMissThatNeverRanTests(unittest.TestCase):
    def test_missing_near_miss_blocks_the_rule(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "missing")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["bdd missing"]))


class CasePromptTests(unittest.TestCase):
    def test_no_case_prompt_contains_another(self):
        """The offline stand-in answers for the first case whose prompt its
        input contains, so a prompt shared across rules grades the wrong rule."""
        self.assertEqual(screen.prompt_clashes([case for rule in screen.load_rules() for case in rule.cases]), [])


class SkillFilesReadTests(unittest.TestCase):
    files = sorted(TREE)

    def events(self, *inputs, status="completed", kind="command"):
        return [{"type": kind, "status": status, "input_summary": text} for text in inputs]

    def test_path_under_any_mount_counts(self):
        read = screen.skill_files_read(
            self.events("sed -n 1,200p .agents/skills/principle-laziness-protocol/SKILL.md")
            + self.events("/tmp/ws/skills/pstack/poteto-mode/SKILL.md", kind="skill_load"),
            self.files,
        )

        self.assertEqual(read, ["poteto-mode/SKILL.md", "principle-laziness-protocol/SKILL.md"])

    def test_cd_into_the_skill_then_reading_counts(self):
        read = screen.skill_files_read(self.events("cd skills/pstack/poteto-mode && cat playbooks/feature.md"), self.files)

        self.assertEqual(read, ["poteto-mode/playbooks/feature.md"])

    def test_listing_and_unfinished_reads_do_not_count(self):
        read = screen.skill_files_read(
            self.events("ls skills/pstack")
            + self.events("cat skills/pstack/poteto-mode/playbooks/feature.md", status="in_progress"),
            self.files,
        )

        self.assertEqual(read, [])


class ExposureRecordTests(unittest.TestCase):
    def test_claude_command_expansion_marks_the_entry_invoked(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "trace.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "<command-name>/poteto-mode</command-name>"}}) + "\n")
            (base / "events.json").write_text(json.dumps({"events": []}))

            self.assertEqual(screen.exposure({"run_base": str(base)}, sorted(TREE)), {"read": [], "entry_invoked": True})


COMPANION = {"SKILL.md": b"---\nname: domain-modeling\n---\n# Domain Modeling\n", "agents/openai.yaml": b"interface:\n  display_name: Domain\n"}


class CompanionMountTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        for path, data in COMPANION.items():
            (base / "companions" / "domain-modeling" / path).parent.mkdir(parents=True, exist_ok=True)
            (base / "companions" / "domain-modeling" / path).write_bytes(data)
        (base / "skill-ci").mkdir()
        (base / "skill-ci" / "runner.lock").write_text("git+https://example.invalid/harness.git@abc123\n")
        environment = mock.patch.dict(os.environ, {"CANON_COMPANIONS_ROOT": str(base / "companions"), "SKILL_CI": str(base / "skill-ci")})
        environment.start()
        self.addCleanup(environment.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.out = base / "out"
        # The rule's workspace cases need the hermes mirror, so build only its pasted-project case.
        rule = screen.load_rule("route-domain-modeling")
        self.rule = dataclasses.replace(rule, cases=tuple(case for case in rule.cases if not case.workspace))

    def arm(self, arm):
        return self.out / "arms" / self.rule.id / self.rule.cases[0].id / arm

    def test_both_arms_mount_the_companion_beside_pstack_as_is(self):
        screen.build(self.out, [self.rule], "poteto-mode")

        for arm in screen.ARMS:
            self.assertEqual(screen.read_tree(self.arm(arm) / "pstack" / "domain-modeling"), COMPANION)
            self.assertTrue((self.arm(arm) / "pstack" / "poteto-mode" / "SKILL.md").is_file())

    def test_single_skill_entry_mounts_and_lists_the_companion(self):
        screen.build(self.out, [self.rule], "skill")

        for arm in screen.ARMS:
            self.assertEqual(screen.read_tree(self.arm(arm) / "skills" / "domain-modeling"), COMPANION)
            manifest = json.loads((self.arm(arm) / screen.MANIFEST).read_text())
            self.assertEqual(manifest["skill_paths"], ["skills/poteto-mode/SKILL.md", "skills/domain-modeling/SKILL.md"])

    def test_build_records_one_companion_hash_for_every_arm(self):
        screen.build(self.out, [self.rule], "poteto-mode")

        record = json.loads((self.out / "arms" / self.rule.id / "build.json").read_text())["companions"]
        digest = screen.tree_hash(COMPANION)
        case = self.rule.cases[0].id
        self.assertEqual(record["trees"]["domain-modeling"], {"files": 2, "sha256": digest, "arms": {f"{case}/current": digest, f"{case}/amended": digest}})

    def test_one_change_check_sees_only_the_pstack_tree(self):
        screen.build(self.out, [self.rule], "poteto-mode")

        built = json.loads((self.out / "arms" / self.rule.id / "build.json").read_text())
        current, amended = ({path: data for path, data in screen.read_tree(self.arm(arm) / "pstack").items() if not path.startswith("domain-modeling/")} for arm in screen.ARMS)
        self.assertEqual((built["target"], built["patch_kind"]), ("poteto-mode/playbooks/feature.md", "insert"))
        self.assertEqual(screen.single_change(current, amended), screen.rule_change(self.rule, screen.tracked("skills")))

    def test_companion_named_like_a_pstack_skill_is_refused(self):
        rule = screen.Rule(self.rule.id, self.rule.source, self.rule.patch, self.rule.target, self.rule.cases, ("poteto-mode",))

        with self.assertRaisesRegex(screen.ScreenError, "companion poteto-mode collides"):
            screen.build(self.out, [rule], "poteto-mode")

    def test_arm_copy_that_differs_from_the_source_is_refused(self):
        with self.assertRaisesRegex(screen.ScreenError, r"differs from its source in \['c/amended'\]"):
            screen.companion_record({"domain-modeling": COMPANION}, {"domain-modeling": {"c/current": screen.tree_hash(COMPANION), "c/amended": "0"}})

    def test_rule_without_companions_builds_as_before(self):
        rule = screen.load_rule("preparatory-refactor")

        screen.build(self.out, [rule], "poteto-mode")

        built = json.loads((self.out / "arms" / rule.id / "build.json").read_text())
        self.assertEqual(sorted(built), ["arms", "cases", "entry", "inserted", "patch_kind", "removed", "target", "tree_dir"])
        self.assertEqual(built["arms"], ["current", "amended"])


INDEX_SENTENCES = {
    "domain-words-index": ("- **Model the Domain**", "Name things with the domain's words from the nearest `CONTEXT.md`, and never use a word it lists under `_Avoid_`."),
    "one-name-per-concept-index": ("- **Model the Domain**", "When the user's word for a concept differs from the code's, use the code's word and tell the user. Do not add a second name."),
    "separate-contexts-index": ("- **Model the Domain**", "When one word names different concepts in two parts of the codebase, keep a separate type for each. Do not merge them."),
    "route-domain-modeling-index": ("- **Feature.**", "When a `CONTEXT.md` exists or the task introduces a new domain term, use the `domain-modeling` skill if available to check the terms and record each resolved one. Otherwise read `CONTEXT.md` and use its terms."),
    "route-codebase-design-index": ("- **Refactoring.**", "When the target moves a seam or deepens shallow modules, use the `codebase-design` skill if available. Otherwise keep a new interface only when a second adapter exists."),
}


class IndexPlacementPatchTests(unittest.TestCase):
    def test_each_index_variant_appends_one_sentence_to_one_entry_of_poteto_mode(self):
        tree = screen.tracked("skills")
        for rule_id, (entry, sentence) in INDEX_SENTENCES.items():
            with self.subTest(rule=rule_id):
                rule = screen.load_rule(rule_id)
                path, _, body = screen.parse_patch(rule.patch)
                change = screen.single_change(tree, screen.apply_patch(tree, rule.patch))

                self.assertEqual((path, change.kind, change.inserted), ("poteto-mode/SKILL.md", "insert", " " + sentence))
                self.assertEqual([tag for tag, _ in body], ["-", "+"])
                self.assertTrue(body[1][1].startswith(entry))
                self.assertTrue(body[1][1].endswith(sentence + "\n"))


class CasesFromTests(unittest.TestCase):
    def test_variant_runs_its_source_cases_under_its_own_id(self):
        source, variant = screen.load_rule("domain-words"), screen.load_rule("domain-words-index")

        self.assertEqual((variant.cases_from, variant.case_rule, variant.source), ("domain-words", "domain-words", "Evans EV-1"))
        self.assertEqual([(case.id, case.kind, case.root) for case in variant.cases], [(case.id, case.kind, case.root) for case in source.cases])
        self.assertEqual({case.rule for case in variant.cases}, {"domain-words-index"})

    def test_variant_inherits_its_source_companions(self):
        self.assertEqual(screen.load_rule("route-domain-modeling-index").companions, ("domain-modeling",))
        self.assertEqual(screen.load_rule("route-codebase-design-index").companions, ("codebase-design",))
        self.assertEqual(screen.load_rule("one-name-per-concept-index").companions, ())


class CasesFromRulesTests(unittest.TestCase):
    """cases_from against a scratch rules directory."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.rules = Path(directory.name)
        patch = FEATURE_HEAD + "@@ -1 +1 @@\n-1. Plan.\n+1. Plan first.\n"
        case = {"cases/shop/case.json": '{"kind": "positive", "domain": "d", "timeout_s": 60, "expected_behavior": ["x"]}',
                "cases/shop/prompt.md": "Add orders.\n{project}", "cases/shop/project/app.py": "x = 1\n"}
        self.write("scratch-base", {"rule.json": '{"source": "S1", "companions": ["domain-modeling"]}', "rule.patch": patch,
                                    "oracle.py": "CHECKS = {'shop': lambda answer, project: []}\n", **case})
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-base"}', "rule.patch": patch})
        self.write("scratch-copy", case)
        rules = mock.patch.object(screen, "RULES", self.rules)
        rules.start()
        self.addCleanup(rules.stop)

    def write(self, rule_id, files):
        for path, text in files.items():
            (self.rules / rule_id / path).parent.mkdir(parents=True, exist_ok=True)
            (self.rules / rule_id / path).write_text(text)

    def test_variant_inherits_source_and_companions(self):
        rule = screen.load_rule("scratch-variant")

        self.assertEqual((rule.source, rule.companions, rule.cases_from), ("S1", ("domain-modeling",), "scratch-base"))

    def test_companions_in_the_variant_override_the_source(self):
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-base", "companions": []}'})

        self.assertEqual(screen.load_rule("scratch-variant").companions, ())

    def test_variant_with_its_own_cases_is_refused(self):
        self.write("scratch-variant", {"cases/other/prompt.md": "Other.\n"})

        with self.assertRaisesRegex(screen.ScreenError, "takes its cases from scratch-base, so it must not have cases"):
            screen.load_rule("scratch-variant")

    def test_variant_of_a_variant_is_refused(self):
        self.write("scratch-third", {"rule.json": '{"cases_from": "scratch-variant"}', "rule.patch": ""})

        with self.assertRaisesRegex(screen.ScreenError, "which takes its own from scratch-base"):
            screen.load_rule("scratch-third")

    def test_unknown_source_is_refused(self):
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-missing"}'})

        with self.assertRaisesRegex(screen.ScreenError, "cases_from must name another rule"):
            screen.load_rule("scratch-variant")

    def test_shared_case_is_no_clash_but_a_copied_prompt_is(self):
        base, variant = screen.load_rule("scratch-base"), screen.load_rule("scratch-variant")
        copy = screen.load_case("scratch-copy", self.rules / "scratch-copy" / "cases" / "shop")

        self.assertEqual(screen.prompt_clashes([*base.cases, *variant.cases]), [])
        self.assertEqual(screen.prompt_clashes([*base.cases, *variant.cases, copy]), [
            "scratch-base/shop inside scratch-copy/shop",
            "scratch-copy/shop inside scratch-base/shop",
            "scratch-copy/shop inside scratch-variant/shop",
            "scratch-variant/shop inside scratch-copy/shop",
        ])


class VariantArmTests(unittest.TestCase):
    def test_variant_arm_grades_with_the_source_oracle_under_its_own_id(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "skill-ci").mkdir()
            (base / "skill-ci" / "runner.lock").write_text("git+https://example.invalid/harness.git@abc123\n")
            rule = screen.load_rule("domain-words-index")
            rule = dataclasses.replace(rule, cases=tuple(case for case in rule.cases if case.id == "shipment-tracking"))
            with mock.patch.dict(os.environ, {"SKILL_CI": str(base / "skill-ci")}), contextlib.redirect_stdout(io.StringIO()):
                screen.build(base / "out", [rule], "poteto-mode")
            arm = base / "out" / "arms" / "domain-words-index" / "shipment-tracking" / "amended"
            samples = ROOT / "rules" / "domain-words" / "cases" / "shipment-tracking" / "samples"
            codes = {}
            for sample in ("good.md", "bad.md"):
                output = base / sample
                output.mkdir()
                (output / "output.md").write_text((samples / sample).read_text())
                codes[sample] = subprocess.run([sys.executable, str(arm / "oracles" / "check.py"), "domain-words-index", "shipment-tracking", str(output)],
                                               capture_output=True, text=True).returncode
            command = json.loads((arm / screen.MANIFEST).read_text())["cases"][0]["assertions"][0]["command"]

            self.assertEqual((arm / "rules" / "domain-words-index" / "oracle.py").read_bytes(), (ROOT / "rules" / "domain-words" / "oracle.py").read_bytes())
            self.assertEqual(command, ["python3", "oracles/check.py", "domain-words-index", "shipment-tracking", "{output_dir}"])
            self.assertEqual(codes, {"good.md": 0, "bad.md": 1})


class AnsweredCaseTests(unittest.TestCase):
    rules = [screen.load_rule("domain-words"), screen.load_rule("domain-words-index")]

    def prompt(self, case_id):
        return "$poteto-mode Task prompt:\n" + screen.render_prompt(next(case for case in self.rules[0].cases if case.id == case_id))

    def test_workspace_path_names_the_rule_and_case(self):
        path = "/o/arms/domain-words-index/session-lineage-usage/amended/workspace"

        rule, case = screen.answered_case(self.rules, self.prompt("session-lineage-usage"), "", path)

        self.assertEqual((rule.id, case.id), ("domain-words-index", "session-lineage-usage"))

    def test_shared_pasted_case_goes_to_the_rule_whose_text_is_mounted(self):
        mounted = "- **Model the Domain** ... " + INDEX_SENTENCES["domain-words-index"][1]

        rule, case = screen.answered_case(self.rules, self.prompt("shipment-tracking"), mounted)

        self.assertEqual((rule.id, case.id), ("domain-words-index", "shipment-tracking"))

    def test_shared_pasted_case_with_no_rule_text_mounted_goes_to_the_first_rule(self):
        rule, case = screen.answered_case(self.rules, self.prompt("shipment-tracking"), "")

        self.assertEqual((rule.id, case.id), ("domain-words", "shipment-tracking"))


if __name__ == "__main__":
    unittest.main()


class SelectCasesTests(unittest.TestCase):
    def test_keeps_only_named_cases_and_drops_empty_rules(self):
        rules = screen.load_rules(["domain-words", "two-hats"])
        chosen = screen.select_cases(rules, ["session-lineage-usage"])
        self.assertEqual([(r.id, [c.id for c in r.cases]) for r in chosen], [("domain-words", ["session-lineage-usage"])])

    def test_unknown_case_is_refused(self):
        with self.assertRaises(SystemExit):
            screen.select_cases(screen.load_rules(["two-hats"]), ["no-such-case"])
