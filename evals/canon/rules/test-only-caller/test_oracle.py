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

    def test_keeping_the_helper_under_an_alias_fails(self):
        good = (RULES / RULE / "cases" / TIDY / "samples" / "good.md").read_text()
        answer = good.replace(
            "    return text[: limit - len(suffix)].rstrip() + suffix\n</file>",
            "    return text[: limit - len(suffix)].rstrip() + suffix\n\n\n"
            "def _banner(text, width=40):\n"
            '    inner = " " + text + " "\n'
            "    if len(inner) >= width:\n"
            "        return inner\n"
            "    pad = width - len(inner)\n"
            '    return "*" * (pad // 2) + inner + "*" * (pad - pad // 2)\n\n\n'
            "banner = _banner\n</file>",
            1,
        )
        self.assertEqual(grade(RULE, TIDY, text=answer), ["banner is still defined though only its tests call it"])

    def test_deleting_the_helper_after_reshaping_the_kept_code_fails(self):
        good = (RULES / RULE / "cases" / TIDY / "samples" / "good.md").read_text()
        _, first, second = good.split("<commit ")
        tests = "<file" + first.split("<file", 2)[2].split("</commit>")[0]
        flattened = second.split("<file", 1)[1].split("</file>")[0]
        banner = (RULES / RULE / "cases" / TIDY / "project" / "textkit" / "format.py").read_text().split("\n\n\ndef banner", 1)[1]
        answer = (
            '<commit message="Flatten slugify and truncate">\n<file' + flattened.rstrip("\n") + "\n\n\ndef banner" + banner + "</file>\n</commit>\n"
            '<commit message="Delete banner, which only its tests call">\n<file' + flattened + "</file>\n" + tests + "</commit>\n"
        )
        self.assertEqual(
            grade(RULE, TIDY, text=answer),
            ["commit 1 ('Flatten slugify and truncate') reshapes slugify or truncate before banner is deleted"],
        )

    def test_deleting_the_tests_before_the_helper_fails(self):
        good = (RULES / RULE / "cases" / TIDY / "samples" / "good.md").read_text()
        _, first, second = good.split("<commit ")
        code, tests = first.split("</file>\n", 1)
        answer = (
            '<commit message="Delete banner tests">\n' + tests.split("</commit>")[0] + "</commit>\n"
            '<commit message="Delete banner">\n<file' + code.split("<file", 1)[1] + "</file>\n</commit>\n<commit " + second
        )
        self.assertEqual(grade(RULE, TIDY, text=answer), ["commit 2 ('Delete banner') deletes banner without its tests"])


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
