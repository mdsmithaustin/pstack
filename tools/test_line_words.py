import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_line_words", ROOT / "tools/check-line-words.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class LongLines(unittest.TestCase):
    def test_counts_a_paragraph_and_a_list_item(self):
        text = "short line\n" + "word " * 151 + "\n- " + "word " * 151
        self.assertEqual(check.long_lines(text), [(2, 151), (3, 152)])

    def test_a_line_at_the_limit_passes(self):
        self.assertEqual(check.long_lines("word " * 150), [])

    def test_code_tables_quotes_and_headings_are_not_instructions(self):
        long = "word " * 200
        text = "\n".join([f"| {long} |", f"> {long}", f"# {long}", "```", long, "```", f"   ```sh\n{long}\n   ```"])
        self.assertEqual(check.long_lines(text), [])

    def test_a_line_after_a_closed_fence_counts_again(self):
        self.assertEqual(check.long_lines("```\ncode\n```\n" + "word " * 151), [(4, 151)])

    def test_a_tilde_fence_is_code_and_only_its_own_marker_closes_it(self):
        long = "word " * 151
        self.assertEqual(check.long_lines(f"~~~\n{long}\n```\n{long}\n~~~\n{long}"), [(6, 151)])

    def test_a_line_that_starts_with_an_issue_number_is_not_a_heading(self):
        long = "word " * 151
        self.assertEqual(check.long_lines(f"#123 {long}\n####### {long}\n###### {long}"), [(1, 152), (2, 152)])

    def test_the_limit_is_a_parameter(self):
        self.assertEqual(check.long_lines("one two three", limit=2), [(1, 3)])


class Repository(unittest.TestCase):
    def test_no_skill_line_runs_past_the_limit(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools/check-line-words.py")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_long_line_fails_with_its_location(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools/check-line-words.py"), "--limit", "5"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r"FAIL line words: skills/\S+\.md:\d+ has \d+ words, above the limit of 5\.")


if __name__ == "__main__":
    unittest.main()
