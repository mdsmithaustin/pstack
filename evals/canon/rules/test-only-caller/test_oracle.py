import unittest

from check import RULES, grade

RULE = "test-only-caller"
TIDY, EXPORTS = "textkit-tidy", "textkit-exports"


class TextkitTidyTests(unittest.TestCase):
    def test_deleting_the_test_only_helper_passes(self):
        self.assertEqual(grade(RULE, TIDY, "good.md"), [])

    def test_keeping_the_test_only_helper_fails(self):
        self.assertEqual(grade(RULE, TIDY, "bad.md"), ["banner is still defined though only its tests call it"])

    def test_deleting_the_helper_but_not_its_tests_fails(self):
        good = (RULES / RULE / "cases" / TIDY / "samples" / "good.md").read_text()
        head, tests_onward = good.split('<file path="tests/test_format.py">', 1)
        answer = head + tests_onward.split("</file>\n", 1)[1]
        self.assertEqual(
            grade(RULE, TIDY, text=answer),
            [
                "suite fails after commit 1 ('Delete banner, which only its tests call')",
                "suite fails after commit 2 ('Drop unused import and flatten slugify and truncate')",
            ],
        )


class TextkitExportsTests(unittest.TestCase):
    def test_keeping_the_exported_helper_passes(self):
        self.assertEqual(grade(RULE, EXPORTS, "good.md"), [])

    def test_deleting_the_exported_helper_fails(self):
        self.assertEqual(
            grade(RULE, EXPORTS, "bad.md"),
            ["textkit.banner is gone or changed, though the package entry point exports it"],
        )


if __name__ == "__main__":
    unittest.main()
