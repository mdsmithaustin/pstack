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

import sandbox  # noqa: E402

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
        rules = [rule for rule in screen.load_rules() if rule.paired]
        self.assertIn("value-type", [rule.id for rule in rules])
        for rule in rules:
            with self.subTest(rule=rule.id):
                change = screen.rule_change(rule, screen.rule_tree(rule))
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


def run_row(verdict, read, entry="not observed"):
    return {"verdict": verdict, "exposure": {"read": read, "entry": entry}}


class PairOutcomeTests(unittest.TestCase):
    target = "principle-laziness-protocol/SKILL.md"

    def test_amended_arm_that_never_read_the_patched_file_is_unexposed_not_a_tie(self):
        outcome = screen.classify(run_row("PASS", [self.target]), run_row("PASS", ["poteto-mode/SKILL.md"], "injected"), self.target)

        self.assertEqual(outcome, "unexposed")

    def test_unexposed_wins_over_an_apparent_separation(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), self.target)

        self.assertEqual(outcome, "unexposed")

    def test_exposed_pairs_are_named_by_their_verdicts(self):
        cases = {("FAIL", "PASS"): "separates", ("PASS", "PASS"): "tie-pass", ("FAIL", "FAIL"): "tie-fail", ("PASS", "FAIL"): "reverses"}
        for (current, amended), expected in cases.items():
            with self.subTest(current=current, amended=amended):
                self.assertEqual(screen.classify(run_row(current, []), run_row(amended, [self.target]), self.target), expected)

    def test_patched_index_counts_as_exposed_when_the_trace_shows_the_injection(self):
        outcome = screen.classify(run_row("FAIL", [], "injected"), run_row("PASS", [], "injected"), "poteto-mode/SKILL.md", "poteto-mode")

        self.assertEqual(outcome, "separates")

    def test_entry_the_trace_never_shows_is_unexposed_under_the_poteto_mode_entry(self):
        """A runner that hid the entry would run every arm with no pstack."""
        for state in ("not observed", "not registered"):
            with self.subTest(state=state):
                outcome = screen.classify(run_row("FAIL", [], state), run_row("PASS", [], state), "poteto-mode/SKILL.md", "poteto-mode")
                self.assertEqual(outcome, "unexposed")

    def test_leaf_read_without_the_entry_is_unexposed_under_the_poteto_mode_entry(self):
        outcome = screen.classify(run_row("FAIL", [], "injected"), run_row("PASS", [self.target], "not registered"), self.target, "poteto-mode")

        self.assertEqual(outcome, "unexposed")

    def test_baseline_without_the_entry_cannot_anchor_a_separation(self):
        outcome = screen.classify(run_row("FAIL", [], "not observed"), run_row("PASS", [self.target], "injected"), self.target, "poteto-mode")

        self.assertEqual(outcome, "unexposed")

    def test_entry_read_by_the_agent_counts_as_seen(self):
        outcome = screen.classify(run_row("FAIL", ["poteto-mode/SKILL.md"], "read"), run_row("PASS", [self.target, "poteto-mode/SKILL.md"], "read"),
                                  self.target, "poteto-mode")

        self.assertEqual(outcome, "separates")

    def test_patched_index_is_unexposed_under_the_single_skill_entry_when_unread(self):
        outcome = screen.classify(run_row("FAIL", []), run_row("PASS", []), "poteto-mode/SKILL.md", "skill")

        self.assertEqual(outcome, "unexposed")

    def test_the_entry_exposes_only_the_index_not_a_leaf(self):
        outcome = screen.classify(run_row("FAIL", [], "injected"), run_row("PASS", [], "injected"), self.target, "poteto-mode")

        self.assertEqual(outcome, "unexposed")

    def test_a_skill_the_treatment_lists_by_description_is_exposed_without_a_read(self):
        """Both arms show the entry, so the listed skill alone decides exposure."""
        listed = ["premortem/SKILL.md"]
        fail, passed = run_row("FAIL", [], "injected"), run_row("PASS", [], "injected")

        self.assertEqual(screen.classify(fail, dict(fail), listed, "poteto-mode", listed), "tie-fail")
        self.assertEqual(screen.classify(fail, passed, listed, "poteto-mode", listed), "separates")
        self.assertEqual(screen.classify(fail, dict(fail), listed, "poteto-mode"), "unexposed")
        self.assertEqual(screen.classify(fail, dict(fail), [self.target], "poteto-mode", listed), "unexposed")

    def test_a_listed_skill_does_not_expose_a_pair_whose_entry_the_trace_never_shows(self):
        listed = ["premortem/SKILL.md"]

        self.assertEqual(screen.classify(run_row("FAIL", []), run_row("FAIL", []), listed, "poteto-mode", listed), "unexposed")
        self.assertEqual(screen.classify(run_row("FAIL", []), run_row("FAIL", []), listed, "skill", listed), "tie-fail")

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


    def test_near_miss_that_never_read_the_change_cannot_show_the_rule_held(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "unexposed")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["bdd unexposed"]))


class NearMissThatNeverRanTests(unittest.TestCase):
    def test_missing_near_miss_blocks_the_rule(self):
        outcomes = [("plain", "positive", "separates"), ("bdd", "near-miss", "missing")]

        self.assertEqual(screen.rule_verdict(outcomes), ("not-separated", ["bdd missing"]))


class CasePromptTests(unittest.TestCase):
    def test_no_case_prompt_contains_another(self):
        """The offline stand-in answers for the first case whose prompt its
        input contains, so a prompt shared across rules grades the wrong rule."""
        cases = [case for rule in screen.load_rules() for case in rule.cases]
        self.assertIn("marketplace-subtotal", [case.id for case in cases])
        self.assertEqual(screen.prompt_clashes(cases), [])


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
            + self.events("cat skills/pstack/poteto-mode/playbooks/feature.md", status="in_progress")
            + self.events("cat skills/pstack/principle-laziness-protocol/SKILL.md"),
            self.files,
        )

        self.assertEqual(read, ["principle-laziness-protocol/SKILL.md"])

    def test_claude_skill_tool_call_counts_as_reading_that_skills_skill_md(self):
        # The shape the harness recorded for Skill("unslop") in a 2026-09-29 review run, with the skill name swapped.
        def skill_call(name, status):
            return {"index": 266, "type": "skill_load", "status": status, "state_source": "provider_status",
                    "raw_ref": {"file": "trace.jsonl", "line": 278}, "raw_result_ref": {"file": "trace.jsonl", "line": 279},
                    "name": "Skill", "input_summary": name, "output_summary": f"Launching skill: {name}", "source": "claude", "otel": {"file.path": name}}

        read = screen.skill_files_read([
            skill_call("principle-laziness-protocol", "in_progress"),
            skill_call("principle-laziness-protocol", "completed"),
            skill_call("plugin:poteto-mode", "completed"),
            skill_call("/unslop", "completed"),
            skill_call("how", "in_progress"),
        ], self.files + ["unslop/SKILL.md", "how/SKILL.md"])

        self.assertEqual(read, ["poteto-mode/SKILL.md", "principle-laziness-protocol/SKILL.md", "unslop/SKILL.md"])

    def test_a_loaded_skill_the_tree_lacks_and_a_full_path_load_are_not_bare_names(self):
        read = screen.skill_files_read(
            [{"type": "skill_load", "status": "completed", "name": "Skill", "input_summary": "commit"}]
            + self.events("/tmp/ws/skills/pstack/poteto-mode/SKILL.md", kind="skill_load"),
            self.files,
        )

        self.assertEqual(read, ["poteto-mode/SKILL.md"])


CLAUDE_INIT = {"type": "system", "subtype": "init", "cwd": "/ws", "skills": ["how", "poteto-mode"], "slash_commands": ["how", "poteto-mode", "compact"]}
CLAUDE_EXPANSION = {"type": "user", "message": {"role": "user", "content": "<command-message>poteto-mode</command-message>\n<command-name>/poteto-mode</command-name>"}}
CODEX_INJECTION = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "<skill>\n<name>poteto-mode</name>\n<path>/ws/.agents/skills/poteto-mode/SKILL.md</path>\n---\nname: poteto-mode\n"}]}}
CODEX_PROMPT = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "$poteto-mode Read and follow the skill file(s) below"}]}}


def jsonl(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


class EntryEvidenceTests(unittest.TestCase):
    """Trace fixtures shaped like the sbx runner's work dir: the harness's
    run dir under runs/, the agent's transcripts under harvest/."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        work = Path(directory.name) / "claude" / "rule" / "case" / "amended"
        self.base = work / "runs" / "case" / "with_skill" / "run-1"
        self.transcripts = work / "harvest" / "case" / "with_skill" / "run-1" / "transcripts"
        self.base.mkdir(parents=True)

    def seen(self, agent, events=()):
        (self.base / "events.json").write_text(json.dumps({"events": list(events)}))
        return screen.exposure({"run_base": str(self.base)}, sorted(TREE), agent)

    def test_claude_entry_registered_and_expanded_in_the_transcript_is_injected(self):
        jsonl(self.base / "trace.jsonl", CLAUDE_INIT)
        jsonl(self.transcripts / "claude" / "-ws" / "session.jsonl", CLAUDE_EXPANSION)

        self.assertEqual(self.seen("claude"), {"read": [], "entry": "injected"})

    def test_claude_entry_registered_and_called_through_the_skill_tool_is_injected(self):
        jsonl(self.base / "trace.jsonl", CLAUDE_INIT)

        self.assertEqual(self.seen("claude", [{"type": "skill_load", "status": "completed", "name": "Skill", "input_summary": "'poteto-mode'"}])["entry"],
                         "injected")

    def test_claude_entry_registered_and_its_index_read_is_read(self):
        jsonl(self.base / "trace.jsonl", CLAUDE_INIT)

        seen = self.seen("claude", [{"type": "file_read", "status": "completed", "input_summary": "/ws/.claude/skills/poteto-mode/SKILL.md"}])

        self.assertEqual(seen, {"read": ["poteto-mode/SKILL.md"], "entry": "read"})

    def test_claude_entry_registered_but_never_loaded_is_not_observed(self):
        jsonl(self.base / "trace.jsonl", CLAUDE_INIT)

        self.assertEqual(self.seen("claude")["entry"], "not observed")

    def test_claude_init_without_the_entry_is_not_registered_even_when_expanded(self):
        jsonl(self.base / "trace.jsonl", {**CLAUDE_INIT, "skills": ["how"], "slash_commands": ["how", "compact"]})
        jsonl(self.transcripts / "claude" / "-ws" / "session.jsonl", CLAUDE_EXPANSION)

        seen = self.seen("claude", [{"type": "file_read", "status": "completed", "input_summary": "/ws/.claude/skills/poteto-mode/SKILL.md"}])

        self.assertEqual(seen["entry"], "not registered")

    def test_claude_trace_without_an_init_event_is_not_registered(self):
        jsonl(self.base / "trace.jsonl", CLAUDE_EXPANSION)

        self.assertEqual(self.seen("claude")["entry"], "not registered")

    def test_codex_rollout_with_the_skill_message_is_injected(self):
        jsonl(self.transcripts / "codex" / "sessions" / "2026" / "09" / "29" / "rollout-2026-09-29T00-00-00-a.jsonl", CODEX_PROMPT, CODEX_INJECTION)

        self.assertEqual(self.seen("codex"), {"read": [], "entry": "injected"})

    def test_codex_rollout_with_only_the_prefixed_prompt_is_not_observed(self):
        jsonl(self.transcripts / "codex" / "sessions" / "2026" / "09" / "29" / "rollout-2026-09-29T00-00-00-a.jsonl", CODEX_PROMPT)

        self.assertEqual(self.seen("codex")["entry"], "not observed")

    def test_codex_without_a_rollout_counts_only_an_index_read(self):
        read = self.seen("codex", [{"type": "command", "status": "completed", "input_summary": "sed -n 1,400p .agents/skills/poteto-mode/SKILL.md"}])

        self.assertEqual(read["entry"], "read")
        self.assertEqual(self.seen("codex")["entry"], "not observed")


COMPANION = {"SKILL.md": b"---\nname: domain-modeling\n---\n# Domain Modeling\n", "agents/openai.yaml": b"interface:\n  display_name: Domain\n"}


class CompanionMountTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        for path, data in COMPANION.items():
            (base / "companions" / "domain-modeling" / path).parent.mkdir(parents=True, exist_ok=True)
            (base / "companions" / "domain-modeling" / path).write_bytes(data)
        environment = mock.patch.dict(os.environ, {"CANON_COMPANIONS_ROOT": str(base / "companions")})
        environment.start()
        self.addCleanup(environment.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.out = base / "out"
        self.rule = dataclasses.replace(screen.load_rule("scenarios-as-success-criteria"), companions=("domain-modeling",))

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
        self.assertEqual(screen.single_change(current, amended), screen.rule_change(self.rule, screen.rule_tree(self.rule)))

    def test_companion_named_like_a_pstack_skill_is_refused(self):
        rule = dataclasses.replace(self.rule, companions=("poteto-mode",))

        with self.assertRaisesRegex(screen.ScreenError, "companion poteto-mode collides"):
            screen.build(self.out, [rule], "poteto-mode")

    def test_arm_copy_that_differs_from_the_source_is_refused(self):
        with self.assertRaisesRegex(screen.ScreenError, r"differs from its source in \['c/amended'\]"):
            screen.companion_record({"domain-modeling": COMPANION}, {"domain-modeling": {"c/current": screen.tree_hash(COMPANION), "c/amended": "0"}})

    def test_rule_without_companions_builds_as_before(self):
        rule = screen.load_rule("value-type")

        screen.build(self.out, [rule], "poteto-mode")

        built = json.loads((self.out / "arms" / rule.id / "build.json").read_text())
        self.assertEqual(sorted(built), ["arms", "cases", "entry", "inserted", "patch_kind", "removed", "target", "tree_dir"])
        self.assertEqual(built["arms"], ["current", "amended"])


SCREENED_AT = "5dea4e2daaaf468d9886abcd63e1f95c74477444"
# The held-cuts screen reads the tree after the 2026-09-24 upstream sync, where the held lines are present.
CUTS_SCREENED_AT = "fcc6c78f5fd29dc9c20cfc8988c11e9bdf05a7b2"
# The spawn-step screen reads the tree after the upstream port through 12d587d.
SPAWN_SCREENED_AT = "4fe213477eda148bbcdfdeea61b5b08209cbc993"
# The hard spawn-step case reads main at 324b3e80, whose skills/ matches 4fe21347.
HARD_SPAWN_SCREENED_AT = "324b3e80f60b09f5247e801129eb4f31b519850f"
# The large-module and deletion-reframe review rules read main at 21d8df2d.
REVIEW_LENS_SCREENED_AT = "21d8df2d547eeaa62317fbbbff89510f06aa0024"
# The premortem placement screen reads main at 9e35d36b.
PREMORTEM_SCREENED_AT = "9e35d36bf5d6fef50a3437a23dc0f12c60b3d05b"
INDEX_SENTENCE = "Name things with the domain's words from the nearest `CONTEXT.md`, and never use a word it lists under `_Avoid_`."


class IndexPlacementPatchTests(unittest.TestCase):
    def test_the_index_variant_appends_one_sentence_to_the_model_the_domain_entry(self):
        rule = screen.load_rule("domain-words-index")
        tree = screen.rule_tree(rule)
        path, _, body = screen.parse_patch(rule.patch)
        change = screen.single_change(tree, screen.apply_patch(tree, rule.patch))

        self.assertEqual((path, change.kind, change.inserted), ("poteto-mode/SKILL.md", "insert", " " + INDEX_SENTENCE))
        self.assertEqual([tag for tag, _ in body], ["-", "+"])
        self.assertTrue(body[1][1].startswith("- **Model the Domain**"))
        self.assertTrue(body[1][1].endswith(INDEX_SENTENCE + "\n"))


class CasesFromTests(unittest.TestCase):
    def test_variant_runs_its_source_cases_under_its_own_id(self):
        source, variant = screen.load_rule("domain-words"), screen.load_rule("domain-words-index")

        self.assertEqual((variant.cases_from, variant.case_rule, variant.source), ("domain-words", "domain-words", "Evans EV-1"))
        self.assertEqual([(case.id, case.kind, case.root) for case in variant.cases], [(case.id, case.kind, case.root) for case in source.cases])
        self.assertEqual({case.rule for case in variant.cases}, {"domain-words-index"})


class ScratchRules(unittest.TestCase):
    """A scratch rules directory with a base rule and its variant."""

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


class CasesFromRulesTests(ScratchRules):
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

    def test_pair_rule_takes_a_chosen_subset_of_an_arms_rule_cases(self):
        case = {"kind": "positive", "domain": "d", "timeout_s": 60, "expected_behavior": ["x"]}
        self.write("scratch-arms", {"rule.json": '{"source": "S2", "arms": ["current", "stub"]}',
                                    "oracle.py": "CHECKS = {'shop': lambda a, p: [], 'till': lambda a, p: []}\n",
                                    **{f"cases/{id}/{name}": text for id in ("shop", "till") for name, text in
                                       (("case.json", json.dumps(case)), ("prompt.md", f"Fix the {id}.\n{{project}}"), ("project/app.py", "x = 1\n"))}})
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-arms", "cases": ["till"]}'})

        rule = screen.load_rule("scratch-variant")

        self.assertEqual((rule.source, rule.case_rule, rule.arm_names, [case.id for case in rule.cases]),
                         ("S2", "scratch-arms", ("current", "amended"), ["till"]))

    def test_case_the_source_lacks_is_refused(self):
        self.write("scratch-variant", {"rule.json": '{"cases_from": "scratch-base", "cases": ["shop", "till"]}'})

        with self.assertRaisesRegex(screen.ScreenError, r"cases must be a list of case ids from scratch-base \['shop'\], not \['shop', 'till'\]"):
            screen.load_rule("scratch-variant")

    def test_a_case_id_that_is_not_a_nonempty_string_is_refused(self):
        for bad in ('{"till": 1}', '["shop"]', '""', "3"):
            with self.subTest(bad=bad):
                self.write("scratch-variant", {"rule.json": f'{{"cases_from": "scratch-base", "cases": [{bad}]}}'})

                with self.assertRaisesRegex(screen.ScreenError, r"cases must be a list of case ids from scratch-base \['shop'\]"):
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


class SkillsAtTests(unittest.TestCase):
    """A rule screens the skills/ tree at the commit its rule.json pins."""

    def test_pinned_rule_reads_each_skill_file_as_git_holds_it_at_that_commit(self):
        rule = screen.load_rule("domain-words")
        path = "principle-model-the-domain/SKILL.md"
        at_commit = subprocess.run(["git", "-C", str(screen.REPO), "show", f"{rule.skills_at}:skills/{path}"],
                                   capture_output=True, check=True).stdout

        tree = screen.rule_tree(rule)

        self.assertEqual(tree[path], at_commit)
        self.assertNotEqual(tree[path], (screen.REPO / "skills" / path).read_bytes())

    def test_every_shipped_rule_pins_the_tree_it_was_screened_against(self):
        screened = (SCREENED_AT, CUTS_SCREENED_AT, SPAWN_SCREENED_AT, HARD_SPAWN_SCREENED_AT, REVIEW_LENS_SCREENED_AT, PREMORTEM_SCREENED_AT)
        self.assertEqual({rule.id: rule.skills_at for rule in screen.load_rules() if rule.skills_at not in screened}, {})


class SkillsAtRulesTests(ScratchRules):
    def test_rule_without_a_pin_reads_the_working_tree(self):
        rule = screen.load_rule("scratch-base")

        self.assertIsNone(rule.skills_at)
        self.assertEqual(screen.rule_tree(rule), screen.tracked("skills"))

    def test_pin_that_is_not_a_full_commit_is_refused(self):
        self.write("scratch-base", {"rule.json": '{"source": "S1", "skills_at": "5dea4e2d"}'})

        with self.assertRaisesRegex(screen.ScreenError, "skills_at must be a full 40-character commit, not '5dea4e2d'"):
            screen.load_rule("scratch-base")

    def test_pin_to_a_commit_the_clone_lacks_is_refused(self):
        self.write("scratch-base", {"rule.json": '{"source": "S1", "skills_at": "' + "0" * 40 + '"}'})

        with self.assertRaisesRegex(screen.ScreenError, "cannot read skills/ at 0{40}"):
            screen.rule_tree(screen.load_rule("scratch-base"))


class HarnessCommandTests(unittest.TestCase):
    def test_harness_runs_the_pinned_skill_ci_from_the_repository_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            seen = base / "seen.json"
            command = base / "bin" / "skill-ci"
            command.parent.mkdir()
            command.write_text(f"#!{sys.executable}\nimport json, os, sys\nopen({str(seen)!r}, 'w').write(json.dumps([sys.argv[1:], os.getcwd()]))\n")
            command.chmod(0o755)
            environment = {"PATH": f"{command.parent}{os.pathsep}{os.environ['PATH']}"}

            with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()) as printed:
                screen.harness("validate", "--strict-leakage", base / "manifest.json")

            argv, cwd = json.loads(seen.read_text())
            self.assertEqual(argv, ["harness", "skill-benchmark", "validate", "--strict-leakage", str(base / "manifest.json")])
            self.assertEqual(Path(cwd).resolve(), screen.REPO.resolve())
            self.assertEqual(printed.getvalue(), f"+ skill-benchmark validate --strict-leakage {base / 'manifest.json'}\n")

    def test_harness_version_is_the_release_pinned_in_skill_ci_toml(self):
        self.assertEqual(screen.harness_version(), "skill-ci v1.0.0")


class VariantArmTests(unittest.TestCase):
    def test_variant_arm_grades_with_the_source_oracle_under_its_own_id(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rule = screen.load_rule("domain-words-index")
            rule = dataclasses.replace(rule, cases=tuple(case for case in rule.cases if case.id == "shipment-tracking"))
            with contextlib.redirect_stdout(io.StringIO()):
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
        mounted = "- **Model the Domain** ... " + INDEX_SENTENCE

        rule, case = screen.answered_case(self.rules, self.prompt("shipment-tracking"), mounted)

        self.assertEqual((rule.id, case.id), ("domain-words-index", "shipment-tracking"))

    def test_shared_pasted_case_with_no_rule_text_mounted_goes_to_the_first_rule(self):
        rule, case = screen.answered_case(self.rules, self.prompt("shipment-tracking"), "")

        self.assertEqual((rule.id, case.id), ("domain-words", "shipment-tracking"))


class SelectCasesTests(unittest.TestCase):
    def test_keeps_only_named_cases_and_drops_empty_rules(self):
        rules = screen.load_rules(["test-only-caller", "two-hats"])
        chosen = screen.select_cases(rules, ["textkit-tidy"])
        self.assertEqual([(r.id, [c.id for c in r.cases]) for r in chosen], [("test-only-caller", ["textkit-tidy"])])

    def test_unknown_case_is_refused(self):
        with self.assertRaises(SystemExit):
            screen.select_cases(screen.load_rules(["two-hats"]), ["no-such-case"])



class ArmSelectionTests(unittest.TestCase):
    """screen.py run --arm, with the agent, the manifest audit, and each arm's
    answer and grade stubbed out, since those shell out to the harness."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name).resolve()
        self.out = base / "out"
        for patch in (
            mock.patch.object(screen, "agent_env", return_value={}),
            mock.patch.object(screen, "check_manifest"),
            mock.patch.object(screen, "run_arm"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def run_screen(self, *arms):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = screen.main(["run", "--agent", "codex", "--out", str(self.out), *(f"--arm={arm}" for arm in arms), "value-type"])
        return code, printed.getvalue()

    def test_unknown_arm_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "^unknown arm\\(s\\): currentt$"):
            self.run_screen("currentt")

    def test_partial_run_writes_no_comparison(self):
        code, printed = self.run_screen("current")

        self.assertEqual(code, 0)
        self.assertIn(f"ran only current; run the other arms into {self.out}, then compare --out {self.out}\n", printed)
        self.assertFalse((self.out / "compare.json").exists())

    def test_every_arm_named_writes_the_comparison(self):
        code, _ = self.run_screen("current", "amended")

        self.assertEqual(code, 0)
        self.assertTrue((self.out / "compare.json").is_file())


LAST_MESSAGE_MISSING = 'sbx cp canon-codex-1035851e:/tmp/canon-last-message.txt failed (1): error: path "/tmp/canon-last-message.txt" not found in container'


class SlotFixture(unittest.TestCase):
    """Slots shaped like sandbox.py wrap's: one numbered dir per run holding
    the workspace.json the wrapper recorded, three runs of one case."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name) / "codex" / "rule" / "case" / "current"
        self.work.mkdir(parents=True)
        rows = [{"run_number": n, "run_dir": f"case/with_skill/run-{n}"} for n in (1, 2, 3)]
        (self.work / "tasks.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))

    def slot(self, number, tree="built", agent_rc=0, **record):
        directory = self.work / "harvest" / f"{number:04d}"
        directory.mkdir(parents=True)
        (directory / "workspace.json").write_text(json.dumps({"tree": tree, "agent_rc": agent_rc, **record}))
        (directory / "workspace.diff").write_text(f"diff {number}\n")

    def mapped(self):
        return sorted(path.name for path in (self.work / "harvest" / "case" / "with_skill").glob("run-*"))


class SlotHarvestTests(SlotFixture):
    def test_a_timed_out_slot_with_the_built_tree_is_mapped_beside_the_others(self):
        self.slot(1, agent_rc=124, error=LAST_MESSAGE_MISSING)
        self.slot(2)
        self.slot(3)

        screen.file_harvest(self.work, "built")

        self.assertEqual(self.mapped(), ["run-1", "run-2", "run-3"])
        self.assertEqual((self.work / "harvest" / "case" / "with_skill" / "run-1" / "workspace.diff").read_text(), "diff 1\n")
        self.assertEqual(sorted(path.name for path in (self.work / "harvest").glob("[0-9]*")), [])

    def test_a_timed_out_slot_on_another_tree_is_still_refused(self):
        self.slot(1, tree="wrong", agent_rc=124, error=LAST_MESSAGE_MISSING)
        self.slot(2)
        self.slot(3)

        with self.assertRaisesRegex(screen.ScreenError, "run-1: workspace tree wrong is not the built built$"):
            screen.file_harvest(self.work, "built")

    def test_any_other_recorded_error_is_refused_and_named_not_called_a_tree_mismatch(self):
        self.slot(1, agent_rc=97, error="sandbox setup: boom")
        self.slot(2)
        self.slot(3)

        with self.assertRaisesRegex(screen.ScreenError, "run-1: the wrapper recorded an error: sandbox setup: boom$"):
            screen.file_harvest(self.work, "built")

    def test_a_missing_last_message_after_a_clean_exit_is_refused(self):
        self.slot(1, agent_rc=0, error=LAST_MESSAGE_MISSING)
        self.slot(2)
        self.slot(3)

        with self.assertRaisesRegex(screen.ScreenError, "the wrapper recorded an error"):
            screen.file_harvest(self.work, "built")

    def test_a_crash_followed_by_the_missing_last_message_is_refused(self):
        self.slot(1, agent_rc=1, error=LAST_MESSAGE_MISSING)
        self.slot(2)
        self.slot(3)

        with self.assertRaisesRegex(screen.ScreenError, "run-1: the wrapper recorded an error: sbx cp .* not found in container$"):
            screen.file_harvest(self.work, "built")

    def test_a_timeout_followed_by_a_different_copy_failure_is_refused(self):
        denied = 'sbx cp canon-codex-1035851e:/tmp/canon-last-message.txt failed (1): error: permission denied'
        self.slot(1, agent_rc=124, error=denied)
        self.slot(2)
        self.slot(3)

        with self.assertRaisesRegex(screen.ScreenError, "run-1: the wrapper recorded an error: sbx cp .* permission denied$"):
            screen.file_harvest(self.work, "built")

    def test_slots_left_after_an_earlier_partial_mapping_fill_the_runs_still_unmapped(self):
        moved = self.work / "harvest" / "case" / "with_skill" / "run-1"
        moved.mkdir(parents=True)
        (moved / "workspace.diff").write_text("diff 1\n")
        self.slot(2, agent_rc=124, error=LAST_MESSAGE_MISSING)
        self.slot(3)

        screen.file_harvest(self.work, "built")

        self.assertEqual(self.mapped(), ["run-1", "run-2", "run-3"])
        self.assertEqual((self.work / "harvest" / "case" / "with_skill" / "run-2" / "workspace.diff").read_text(), "diff 2\n")

    def test_the_error_sandbox_py_records_for_a_failed_last_message_copy_is_the_one_tolerated(self):
        failed = subprocess.CompletedProcess([], 1, b"", b'error: path "/tmp/canon-last-message.txt" not found in container')
        with mock.patch.object(sandbox.subprocess, "run", return_value=failed), self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.Sandbox("canon-codex-1035851e").get(sandbox.LAST_MESSAGE, "last-message.txt")

        self.assertTrue(screen.last_message_missing({"agent_rc": 124, "error": str(caught.exception)}))

    def test_a_slot_count_that_fits_neither_all_nor_the_unmapped_runs_is_refused(self):
        self.slot(1)
        self.slot(2)

        with self.assertRaisesRegex(screen.ScreenError, "filled 2 harvest slot\\(s\\) for 3 unharvested of 3 run\\(s\\)"):
            screen.file_harvest(self.work, "built")


class RegradePartialHarvestTests(SlotFixture):
    """screen.py regrade on an arm the harness never graded: the timed-out run
    and the partly mapped layout both regrade from the diff."""

    def setUp(self):
        super().setUp()
        self.out = self.work.parents[3]
        arms = self.out / "arms" / "rule"
        arms.mkdir(parents=True)
        (arms / "build.json").write_text(json.dumps({"cases": {"case": {"workspace": {"tree": "built"}}}}))
        for name in ("run-1", "run-2", "run-3"):
            (self.work / "runs" / "case" / "with_skill" / name).mkdir(parents=True)

    def regraded(self):
        with mock.patch.object(screen, "refuse_leaks"), mock.patch.object(screen, "load_check"), mock.patch.object(screen, "compare"), \
                mock.patch.object(screen, "regrade_run", return_value=("PASS", "")):
            screen.regrade(self.out)
        return json.loads((self.work / "regrade.json").read_text())["results"]

    def test_an_arm_with_a_timed_out_run_regrades_every_run_from_its_diff(self):
        self.slot(1, agent_rc=124, error=LAST_MESSAGE_MISSING)
        self.slot(2)
        self.slot(3)

        rows = self.regraded()

        self.assertEqual([(row["run"], row["verdict"], row["graded_from_diff"]) for row in rows], [(1, "PASS", True), (2, "PASS", True), (3, "PASS", True)])

    def test_a_partly_mapped_harvest_regrades_every_run(self):
        (self.work / "harvest" / "case" / "with_skill" / "run-1").mkdir(parents=True)
        self.slot(2, agent_rc=124, error=LAST_MESSAGE_MISSING)
        self.slot(3)

        self.assertEqual([row["run"] for row in self.regraded()], [1, 2, 3])

    def test_a_second_regrade_of_a_fully_mapped_arm_regrades_again(self):
        self.slot(1)
        self.slot(2)
        self.slot(3)
        self.regraded()

        self.assertEqual([row["run"] for row in self.regraded()], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
