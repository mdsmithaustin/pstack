import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tally.__main__ import main, tally

SAMPLE = Path(__file__).resolve().parents[1] / "sample.txt"


class Tally(unittest.TestCase):
    def test_counts_words_case_insensitively(self):
        counts = tally(["The cat", "the CAT sat"])
        self.assertEqual(counts["the"], 2)
        self.assertEqual(counts["cat"], 2)

    def test_top_limits_the_output(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main([str(SAMPLE), "--top", "1"])
        self.assertEqual(out.getvalue().split(), ["4", "the"])


if __name__ == "__main__":
    unittest.main()
