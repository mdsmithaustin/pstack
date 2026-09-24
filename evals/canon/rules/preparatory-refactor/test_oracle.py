import re
import unittest

from check import RULES, grade

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
