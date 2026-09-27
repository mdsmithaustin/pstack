import importlib.util
import json
import sys
import unittest

from check import RULES, grade, load_oracle
from shared import Workspace, plain_test_failures

RULE, CASE = "refactor-review-diff", "lint-report-loop"
_spec = importlib.util.spec_from_file_location("canon_workspace_refactor_review_diff", RULES.parent / "workspace.py")
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
class LintReportLoopTests(unittest.TestCase):
    def test_held_output_matches_the_pinned_scripts(self):
        load_oracle(RULE)
        oracle = sys.modules[f"canon_oracle_{RULE}"]
        checkout = sample_workspace("").checkout
        tree = {path: (checkout / path).read_text(encoding="utf-8") for path in oracle.PACKAGE}
        self.assertEqual(plain_test_failures({**tree, "held_output.py": oracle.HELD_OUTPUT}, ["held_output"]), [])

    def test_shared_loop_with_a_per_script_formatter_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(sample_diff("good.diff"))), [])

    def test_shared_label_drops_the_asyncio_hint_line(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff"))),
            ["held_output::test_asyncio_report_keeps_a_hint_after_every_hit failed"],
        )

    def test_no_change_is_not_the_refactor(self):
        self.assertEqual(
            grade(RULE, CASE, "good.md", workspace=sample_workspace("")),
            [
                "dev/lint/_framework.py is unchanged or deleted",
                "dev/lint/lint_no_skipped_tests.py main still loops over its arguments",
                "dev/lint/lint_no_global_asyncio_patch.py main still loops over its arguments",
            ],
        )


if __name__ == "__main__":
    unittest.main()
