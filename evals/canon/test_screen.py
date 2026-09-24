import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

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
        for rule in screen.load_rules():
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


if __name__ == "__main__":
    unittest.main()
