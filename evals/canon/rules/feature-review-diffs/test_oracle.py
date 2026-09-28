import importlib.util
import json
import unittest

from check import RULES, grade
from shared import Workspace

RULE, CASE = "feature-review-diffs", "no-debugger-lint"
_spec = importlib.util.spec_from_file_location("canon_workspace_feature_review_diffs", RULES.parent / "workspace.py")
workspace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workspace)
OMNIGENT = "02969a131c72d74c00c5800d8e82ae831f8ec5e5"


def sample_workspace(diff):
    root = RULES / RULE / "cases" / CASE
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    checkout, _ = workspace.reference_checkout(spec)
    return Workspace(checkout, diff)


def sample_diff(name):
    return (RULES / RULE / "cases" / CASE / "samples" / name).read_text(encoding="utf-8")


@unittest.skipUnless(workspace.has_commit(workspace.mirror_path("omnigent"), OMNIGENT),
                     f"needs omnigent {OMNIGENT} in the mirror; run workspace.py fetch omnigent")
class NoDebuggerLintTests(unittest.TestCase):
    def test_ast_rule_with_suppression_and_registration_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(sample_diff("good.diff"))), [])

    def test_line_regex_flags_strings_and_ignores_the_disable_comment(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff"))),
            [
                "held_behavior::test_strings_comments_and_lookalike_names_pass failed",
                "held_behavior::test_disable_comment_silences_the_line failed",
            ],
        )

    def test_unregistered_rule_fails_registration(self):
        good = sample_diff("good.diff")
        module_start = good.index("diff --git a/dev/lint/lint_no_debugger.py")
        self.assertTrue(good.startswith("diff --git a/dev/lint/custom_lint.py"))
        self.assertEqual(
            grade(RULE, CASE, "good.md", workspace=sample_workspace(good[module_start:])),
            ["held_behavior::test_registered_after_the_existing_rules failed"],
        )

    def test_no_change_is_missing_the_rule(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace("")), ["dev/lint/lint_no_debugger.py is missing"])


if __name__ == "__main__":
    unittest.main()
