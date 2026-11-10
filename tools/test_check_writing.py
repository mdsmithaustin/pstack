import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/poteto-mode/scripts/check-writing.py"
GOOD_BODY = "## Why\n\nThe gate repeated.\n\n## What changed\n\n- Bind evidence to a tree.\n\n## Scope\n\nGates only.\n\n## Blast Radius\n\nOne script.\n\n## Verification\n\n- `unittest` passed.\n"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class Writing(unittest.TestCase):
    def check(self, kind, text, *flags):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.md"
            path.write_text(text, encoding="utf-8")
            return run(kind, str(path), *flags)

    def test_conventional_title_passes(self):
        for title in ("fix(pstack): retarget opening-a-pr babysit trigger", "docs: explain routes", "feat(api)!: drop v1"):
            with self.subTest(title=title):
                self.assertEqual(run("title", title).returncode, 0, run("title", title).stdout)

    def test_bad_titles_fail(self):
        for title in ("Fix the thing", "fix(pstack): retarget trigger.", "fix:no space", "update(x): y"):
            with self.subTest(title=title):
                self.assertEqual(run("title", title).returncode, 1)

    def test_default_body_passes(self):
        done = self.check("body", GOOD_BODY)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "PASS"))

    def test_optional_sections_are_allowed_in_place(self):
        body = GOOD_BODY.replace("## Blast Radius", "## Departures from existing patterns\n\nNone.\n\n## Tradeoffs\n\nNone.\n\n## Blast Radius")
        self.assertEqual(self.check("body", body).stdout.strip(), "PASS")

    def test_missing_and_misordered_headings_fail(self):
        missing = self.check("body", GOOD_BODY.replace("## Scope\n\nGates only.\n\n", ""))
        self.assertEqual(missing.returncode, 1)
        self.assertIn("missing `## Scope`", missing.stdout)
        swapped = GOOD_BODY.replace("## Why", "## X").replace("## Verification", "## Why").replace("## X", "## Verification")
        self.assertIn("out of order", self.check("body", swapped).stdout)

    def test_headings_inside_a_code_fence_do_not_count(self):
        example = GOOD_BODY.replace("- Bind evidence to a tree.", "- Bind evidence to a tree.\n\n```md\n## Why\n```")
        self.assertEqual(self.check("body", example).stdout.strip(), "PASS")
        fenced_only = "```md\n" + GOOD_BODY + "```\n"
        done = self.check("body", fenced_only)
        self.assertEqual(done.returncode, 1)
        self.assertIn("missing `## Why`", done.stdout)

    def test_a_shorter_fence_inside_a_longer_one_stays_code(self):
        nested = "Text.\n\n````md\n```\nx \u2014 y\n```\nstill code \u2014 here\n````\n\nAfter the block.\n"
        self.assertEqual(self.check("prose", nested).stdout.strip(), "PASS")

    def test_a_mismatched_closer_does_not_reopen_prose_early(self):
        text = "```\ncode \u2014 one\n~~~\ncode \u2014 two\n```\nProse \u2014 here.\n"
        done = self.check("prose", text)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout.count("FAIL"), 1)
        self.assertIn("FAIL line 6", done.stdout)

    def test_no_headings_skips_the_layout_for_a_repository_template(self):
        self.assertEqual(self.check("body", "## Summary\n\nDone.\n", "--no-headings").returncode, 0)

    def test_long_dash_fails_outside_code_only(self):
        self.assertEqual(self.check("prose", "It works — mostly.\n").returncode, 1)
        self.assertEqual(self.check("prose", "Run `a — b`.\n\n```\nx — y\n```\n").returncode, 0)

    def test_connector_colon_is_a_review_note_not_a_failure(self):
        done = self.check("prose", "The fix is simple: we retry.\n")
        self.assertEqual(done.returncode, 0)
        self.assertIn("review line 1", done.stdout)

    def test_list_colons_urls_and_bold_leads_are_quiet(self):
        text = "It checks three things:\n\n- one\n\nSee https://example.com/a: b for more.\n**Verification.** End to end.\n| a: b | c |\n"
        self.assertEqual(self.check("prose", text).stdout.strip(), "PASS")

    def test_unreadable_file_is_a_usage_error(self):
        self.assertEqual(run("prose", "/nonexistent/file.md").returncode, 2)


if __name__ == "__main__":
    unittest.main()
