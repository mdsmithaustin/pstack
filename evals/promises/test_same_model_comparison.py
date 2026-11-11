#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest

import oracles
from oracles import FAIL, INCONCLUSIVE
from test_oracles import bash, grade, load_case, minimal, read
from test_scripts import RESOLVER, SKILLS, ResolverSandbox

ROLES = ("arena runners", "architect runners", "interrogate reviewers")


def marks(arms):
    return {a["role"]: a["comparison"] for a in arms if "comparison" in a}


class SameModelComparisonPromise(ResolverSandbox):
    def test_same_model_design_comparison_skipped(self):
        self.write_user(
            "arena runners, architect runners: opus@high, opus@max\n"
            "arena cross-judge pool: opus@xhigh\ninterrogate reviewers: opus, opus\n"
        )
        self.assertEqual(
            marks(self.resolve("claude-code", "--lead-model", "opus@medium", *ROLES)),
            {"arena runners": "skip", "architect runners": "skip"},
        )
        self.assertEqual(marks(self.resolve("claude-code", "--lead-model", "sonnet", *ROLES)), {})
        self.write_user("arena runners, architect runners: opus, sonnet\narena cross-judge pool: opus\n")
        self.assertEqual(marks(self.resolve("claude-code", "--lead-model", "opus", *ROLES)), {})
        (self.home / ".agents" / "pstack-models.md").unlink()
        self.assertEqual(
            marks(self.resolve("hermes", *ROLES)), {"arena runners": "skip", "architect runners": "skip"},
        )
        roles_md = (SKILLS / "pstack-harness/references/roles.md").read_text(encoding="utf-8")
        for rule in (
            "On `skip` in a design comparison, spawn no runner and no cross-judge.",
            "state in the reply `same-model, comparison skipped` with the model",
            "For this check, effort is not a model: two arms, or an arm and you, that differ only in effort are one model",
            "The skip covers the comparison only.",
            "Run a design comparison despite `skip` only when the user asked for the comparison itself in this task",
        ):
            self.assertIn(rule, roles_md)
        for skill in ("arena", "architect"):
            self.assertIn('`"comparison": "skip"`', (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8"))

    def test_a_review_that_runs_through_arena_keeps_its_arms_on_a_marked_row(self):
        review = "still run every arm of a review or second opinion, labeled same-model"
        for harness, lead in (("grok", ("--lead-model", "grok-4.7")), ("hermes", ())):
            with self.subTest(harness=harness):
                arena = self.resolve(harness, *lead, "arena runners")[0]
                architect = self.resolve(harness, *lead, "architect runners")[0]
                self.assertEqual((arena["comparison"], architect["comparison"]), ("skip", "skip"))
                self.assertEqual([review in note for note in arena["notes"]].count(True), 1)
                self.assertNotIn(review, " ".join(architect["notes"]))
        roles_md = (SKILLS / "pstack-harness/references/roles.md").read_text(encoding="utf-8")
        self.assertIn(
            "ignore the field: run every runner arm, let arena's Phase C choose or skip the judge, "
            "and label the result `same-model` in the verdict and the reply",
            roles_md,
        )
        self.assertNotIn("every rule that compares models", roles_md)
        self.assertIn(
            "a design comparison skips Phases B through E, and a review still runs them",
            (SKILLS / "arena/SKILL.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'When the resolver prints `"comparison": "skip"`, still run every arm and label the result `same-model`.',
            (SKILLS / "blast-radius/SKILL.md").read_text(encoding="utf-8"),
        )

    def test_the_one_model_note_without_the_field_is_what_triggers_the_rerun(self):
        self.write_user("arena runners, architect runners, arena cross-judge pool: opus, opus\n")
        first = self.resolve("claude-code", "architect runners")[0]
        self.assertNotIn("comparison", first)
        self.assertIn("architect runners resolves to one distinct model (opus)", first["notes"][0])
        self.assertIn(
            'When the arm has no `"comparison"` field and a note says that either role resolves to one distinct model, '
            "rerun with `--lead-model '<model>'`",
            (SKILLS / "pstack-harness/references/roles.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            marks(self.resolve("claude-code", "--lead-model", "opus", "architect runners")),
            {"architect runners": "skip"},
        )

    def test_a_panel_that_all_inherits_is_a_skip_for_any_lead(self):
        for lead in ((), ("--lead-model", "auto"), ("--lead-model", "opus")):
            with self.subTest(lead=lead):
                self.assertEqual(
                    marks(self.resolve("hermes", *lead, "arena runners", "architect runners")),
                    {"arena runners": "skip", "architect runners": "skip"},
                )
        self.assertIn(
            "When at least one arm names a model, a lead model of `auto` or `inherit-parent`, "
            "or one this CLI cannot use, gets a note and no result.",
            (SKILLS / "setup-pstack/references/models-config.md").read_text(encoding="utf-8"),
        )

    def test_a_mixed_panel_without_the_flag_gets_no_mark_and_no_note(self):
        self.write_user("arena runners, architect runners: opus, inherit-parent\narena cross-judge pool: opus\n")
        for role in ("arena runners", "architect runners"):
            with self.subTest(role=role):
                arms = self.resolve("claude-code", role)
                self.assertEqual([(a.get("comparison"), a.get("notes")) for a in arms], [(None, None), (None, None)])
                self.assertEqual(marks(self.resolve("claude-code", "--lead-model", "opus", role)), {role: "skip"})


class ArchitectOracleReadsTheResolver(ResolverSandbox):
    REPLY = "Designed the import pipeline myself: same-model, comparison skipped (opus)."

    def setUp(self):
        super().setUp()
        self.write_user("arena runners: opus, sonnet\narchitect runners, arena cross-judge pool: opus, opus\n")

    def resolver_call(self, seq, *args, ok=True):
        argv = [sys.executable, RESOLVER, "--resolve", "--harness", "claude-code", "--project", self.project, *args]
        head = self.run_cmd(argv, expect=0).stdout[:oracles.RESULT_HEAD]
        return bash(seq, "python3 check-models-config.py --resolve --harness claude-code " + " ".join(args), ok, head)

    def graded(self, *calls):
        events = [read(5, "arena/SKILL.md"), *(event for call in calls for event in call)]
        trace = minimal(events=events, final_reply=self.REPLY)
        return grade("architect-runs-arena-for-sketches", trace, load_case("architect-run"))

    def test_a_reported_skip_the_resolver_marked_is_inconclusive(self):
        result = self.graded(self.resolver_call(7, "--lead-model", "opus", "architect runners"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("the resolver marked the comparison `skip`", result["failures"][0])

    def test_a_reported_skip_the_resolver_did_not_mark_fails(self):
        for flags in ((), ("--lead-model", "sonnet")):
            with self.subTest(flags=flags):
                result = self.graded(self.resolver_call(7, *flags, "architect runners"))
                self.assertEqual(result["verdict"], FAIL, result)

    def test_a_rerun_that_marks_the_skip_replaces_the_first_resolve(self):
        result = self.graded(
            self.resolver_call(7, "architect runners"),
            self.resolver_call(9, "--lead-model", "opus", "architect runners"),
        )
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("the resolver marked the comparison `skip`", result["failures"][0])

    def test_a_rerun_of_every_role_that_marks_the_skip_replaces_the_first_resolve(self):
        result = self.graded(self.resolver_call(7, "architect runners"), self.resolver_call(9, "--lead-model", "opus"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("the resolver marked the comparison `skip`", result["failures"][0])

    def test_a_marked_resolve_stands_when_a_later_resolve_omits_the_lead_model(self):
        for later in ((), ("architect runners",)):
            with self.subTest(later=later):
                result = self.graded(
                    self.resolver_call(7, "--lead-model", "opus", "architect runners"), self.resolver_call(9, *later),
                )
                self.assertEqual(result["verdict"], INCONCLUSIVE, result)
                self.assertIn("the resolver marked the comparison `skip`", result["failures"][0])

    def test_a_cut_off_resolve_with_the_lead_model_keeps_a_later_unmarked_row_inconclusive(self):
        result = self.graded(
            self.resolver_call(
                7, "--lead-model", "opus", "trail reviewer", "feature", "how explorer", "arena runners",
                "architect runners",
            ),
            self.resolver_call(9, "architect runners"),
        )
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("no resolver output in the trace shows", result["failures"][0])

    def test_a_later_resolve_with_the_lead_model_that_drops_the_mark_fails(self):
        marked = self.resolver_call(7, "--lead-model", "opus", "architect runners")
        self.write_user("architect runners: opus, sonnet\narena cross-judge pool: opus\n")
        result = self.graded(marked, self.resolver_call(9, "--lead-model", "opus", "architect runners"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_an_arena_skip_does_not_excuse_an_unmarked_architect_skip(self):
        self.write_user("architect runners: sonnet, sonnet\narena runners, arena cross-judge pool: opus, opus\n")
        for roles in (
            (("architect runners",), ("arena runners",)),
            (("arena runners",), ("architect runners",)),
            (("architect runners", "arena runners"),),
        ):
            with self.subTest(roles=roles):
                result = self.graded(*(
                    self.resolver_call(7 + 2 * i, "--lead-model", "opus", *group)
                    for i, group in enumerate(roles)
                ))
                self.assertEqual(result["verdict"], FAIL, result)

    def test_a_reported_skip_with_no_readable_resolver_row_is_inconclusive(self):
        cases = {
            "no resolver call": (),
            "failed resolver call": (self.resolver_call(7, "architect runners", ok=False),),
            "only the arena row": (self.resolver_call(7, "arena runners"),),
            "architect row cut off": (self.resolver_call(7, "trail reviewer", "feature", "how explorer", "arena runners", "architect runners"),),
        }
        for name, calls in cases.items():
            with self.subTest(name):
                result = self.graded(*calls)
                self.assertEqual(result["verdict"], INCONCLUSIVE, result)
                self.assertIn("no resolver output in the trace shows", result["failures"][0])


if __name__ == "__main__":
    unittest.main()
