import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tally.__main__ import main

SAMPLE = Path(__file__).resolve().parent.parent / "sample.txt"


class MinCountTest(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            main([str(SAMPLE), *args])
        return out.getvalue()

    def test_default_output_is_unchanged(self):
        self.assertEqual(self.run_cli("--min-count", "1"), self.run_cli())

    def test_hides_rare_words(self):
        counts = [int(line.split()[0]) for line in self.run_cli("--top", "50", "--min-count", "3").splitlines()]
        self.assertTrue(counts and min(counts) >= 3)


if __name__ == "__main__":
    unittest.main()
