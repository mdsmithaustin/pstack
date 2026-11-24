import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tally.__main__ import main, tally, to_json

SAMPLE = Path(__file__).resolve().parent.parent / "sample.txt"


class Tally(unittest.TestCase):
    def test_counts_words_case_insensitively(self):
        counts = tally(["The cat", "the dog"])
        self.assertEqual(counts["the"], 2)

    def test_text_output_is_stable(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main([str(SAMPLE), "--top", "2"])
        self.assertEqual(out.getvalue(), "    4  the\n    2  cat\n")

    def test_json_lists_top_words_with_counts(self):
        counts = tally(SAMPLE.read_text(encoding="utf-8").splitlines())
        self.assertEqual(json.loads(to_json(counts, 2)), [{"word": "the", "count": 4}, {"word": "cat", "count": 2}])


if __name__ == "__main__":
    unittest.main()
