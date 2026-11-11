#!/usr/bin/env python3
from __future__ import annotations

import unittest

from test_scripts import SKILLS, ResolverSandbox


class SameModelComparisonPromise(ResolverSandbox):
    def test_same_model_design_comparison_skipped(self):
        self.write_user(
            "arena runners, architect runners: opus@high, opus@max\n"
            "arena cross-judge pool: opus@xhigh\ninterrogate reviewers: opus, opus\n"
        )
        roles = ("arena runners", "architect runners", "interrogate reviewers")

        def marks(arms):
            return {a["role"]: a["comparison"] for a in arms if "comparison" in a}

        self.assertEqual(
            marks(self.resolve("claude-code", "--lead-model", "opus@medium", *roles)),
            {"arena runners": "skip", "architect runners": "skip"},
        )
        self.assertEqual(marks(self.resolve("claude-code", "--lead-model", "sonnet", *roles)), {})
        self.write_user("arena runners, architect runners: opus, sonnet\narena cross-judge pool: opus\n")
        self.assertEqual(marks(self.resolve("claude-code", "--lead-model", "opus", *roles)), {})
        (self.home / ".agents" / "pstack-models.md").unlink()
        self.assertEqual(
            marks(self.resolve("hermes", *roles)), {"arena runners": "skip", "architect runners": "skip"},
        )
        roles_md = (SKILLS / "pstack-harness/references/roles.md").read_text(encoding="utf-8")
        for rule in (
            "On `skip`, spawn no runner and no cross-judge.",
            "state in the reply `same-model, comparison skipped` with the model",
            "that differ only in effort are one model",
            "The skip covers the comparison only.",
            "with its reviewer on a model at or above your tier",
            "Run the panel despite `skip` only when the user asked for the comparison itself in this task",
        ):
            self.assertIn(rule, roles_md)
        for skill in ("arena", "architect"):
            self.assertIn('`"comparison": "skip"`', (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
