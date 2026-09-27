import importlib.util
import json
import unittest

from check import RULES, grade
from shared import Workspace

RULE, CASE = "nearby-validation", "paste-markers"
_spec = importlib.util.spec_from_file_location("canon_workspace_nearby_validation", RULES.parent / "workspace.py")
workspace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workspace)
HERMES = "130b8f2c5dbca93a81aa396dd2ba44420d78f6f0"
ADJACENT = ("tests.hermes_cli.test_input_sanitize::TestStripLeakedBracketedPasteWrappers::"
            "test_does_not_strip_non_wrapper_bracket_forms_in_normal_text failed")
REPORTED = [
    "reported_paste::test_opening_marker_glued_to_a_typed_word failed",
    "reported_paste::test_glued_paste_followed_by_more_typing failed",
    "reported_paste::test_two_glued_pastes failed",
]
LOOSENED_TEST = """diff --git a/tests/hermes_cli/test_input_sanitize.py b/tests/hermes_cli/test_input_sanitize.py
--- a/tests/hermes_cli/test_input_sanitize.py
+++ b/tests/hermes_cli/test_input_sanitize.py
@@ -16,7 +16,7 @@ class TestStripLeakedBracketedPasteWrappers:
 
     def test_does_not_strip_non_wrapper_bracket_forms_in_normal_text(self):
         text = "literal[200~tag and literal[201~tag should stay"
-        assert strip_leaked_bracketed_paste_wrappers(text) == text
+        assert strip_leaked_bracketed_paste_wrappers(text) == "literaltag and literal[201~tag should stay"
 
 
 class TestCollapseRepeatedInputArtifacts:
"""


def sample_workspace(diff):
    root = RULES / RULE / "cases" / CASE
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    checkout, _ = workspace.reference_checkout(spec)
    return Workspace(checkout, diff)


def sample_diff(name):
    return (RULES / RULE / "cases" / CASE / "samples" / name).read_text(encoding="utf-8")


@unittest.skipUnless(workspace.has_commit(workspace.mirror_path("hermes"), HERMES),
                     f"needs hermes {HERMES} in the mirror; run workspace.py fetch hermes")
class PasteMarkersTests(unittest.TestCase):
    def test_paired_fix_passes_the_pinned_modules_and_the_report(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(sample_diff("good.diff"))), [])

    def test_unconditional_strip_breaks_the_adjacent_literal_test(self):
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff"))), [ADJACENT])

    def test_loosening_the_adjacent_test_does_not_hide_the_break(self):
        diff = sample_diff("bad.diff") + LOOSENED_TEST
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(diff)), [ADJACENT])

    def test_no_change_fails_only_the_reported_cases(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace("")), REPORTED)


if __name__ == "__main__":
    unittest.main()
