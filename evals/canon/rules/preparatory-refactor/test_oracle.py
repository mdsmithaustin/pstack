import difflib
import json
import re
import sys
import unittest

from check import RULES, grade
from shared import Workspace, apply_diff

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE, CASE = "preparatory-refactor", "csv-export"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class CsvExportTests(unittest.TestCase):
    def test_restructure_then_feature_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_multiline_commit_messages_parse(self):
        good = (SAMPLES / "good.md").read_text(encoding="utf-8")
        multiline = re.sub(r'<commit message="([^"]*)">', r'<commit message="\1\n\nBody line.">', good)
        self.assertNotEqual(multiline, good)
        self.assertEqual(grade(RULE, CASE, text=multiline), [])

    def test_single_commit_with_threaded_flag_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            ["answer has 1 commit(s); the restructure is not its own commit"],
        )

    def test_feature_before_restructure_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "feature-first.md"),
            ["commit 1 ('Add CSV export') adds the feature; no restructure lands first"],
        )


def omnigent_checkout(case):
    root = RULES / RULE / "cases" / case
    return workspace.reference_checkout(workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"]))[0]


def omnigent_mirror():
    return workspace.has_commit(workspace.mirror_path("omnigent"), "02969a131c72d74c00c5800d8e82ae831f8ec5e5")


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class PiiIpAddressTests(unittest.TestCase):
    CASE = "pii-ip-address"

    def sample(self, name):
        diff = (RULES / RULE / "cases" / self.CASE / "samples" / f"{name}.diff").read_text()
        return grade(RULE, self.CASE, f"{name}.md", workspace=Workspace(omnigent_checkout(self.CASE), diff))

    def test_one_category_table_then_one_new_entry_passes(self):
        self.assertEqual(self.sample("good"), [])

    def test_ip_key_added_to_every_hand_list_fails(self):
        self.assertEqual(
            self.sample("bad"),
            [
                "omnigent/policies/builtins/safety.py lists the PII category keys by hand in 4 places: "
                "_PII_CATEGORY_PATTERNS, _PII_CATEGORY_LABELS, POLICY_REGISTRY enum, POLICY_REGISTRY default"
            ],
        )

    def test_untouched_checkout_fails(self):
        self.assertEqual(
            grade(RULE, self.CASE, text="Done.", workspace=Workspace(omnigent_checkout(self.CASE), "")),
            [
                "no PII category key for IP addresses is added",
                "omnigent/policies/builtins/safety.py lists the PII category keys by hand in 4 places: "
                "_PII_CATEGORY_PATTERNS, _PII_CATEGORY_LABELS, POLICY_REGISTRY enum, POLICY_REGISTRY default",
            ],
        )

    def test_restructure_with_an_ip_key_outside_the_category_table_fails(self):
        checkout = omnigent_checkout(self.CASE)
        good = (RULES / RULE / "cases" / self.CASE / "samples" / "good.diff").read_text()
        safety = "omnigent/policies/builtins/safety.py"
        restructured = re.sub(r'\n    "ip_address": _PiiCategory\(.*?\n    \),', "", apply_diff(checkout, good)[safety].decode(), flags=re.DOTALL)
        self.assertNotIn('"ip_address"', restructured)
        context = "omnigent/policies/builtins/context.py"
        edits = {safety: restructured, context: (checkout / context).read_text(encoding="utf-8") + '\nAUDIT_FIELD = "ip_address"\n'}
        diff = "".join("".join(difflib.unified_diff((checkout / path).read_text(encoding="utf-8").splitlines(True),
                                                    new.splitlines(True), f"a/{path}", f"b/{path}"))
                       for path, new in edits.items())
        self.assertEqual(
            grade(RULE, self.CASE, text="Added the IP address category.", workspace=Workspace(checkout, diff)),
            ["no PII category key for IP addresses is added"],
        )
