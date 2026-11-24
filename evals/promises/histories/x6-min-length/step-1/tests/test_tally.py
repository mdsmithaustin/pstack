import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tally.__main__ import main, tally


def run(*args, text="the cat sat on the mat\nthe dog sat on the log\na cat and a dog\n"):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "in.txt"
        path.write_text(text, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(path), *args])
    return out.getvalue()


class Tally(unittest.TestCase):
    def test_counts_words_case_insensitively(self):
        self.assertEqual(tally(["The cat", "the CAT"])["cat"], 2)

    def test_prints_the_most_common_words_first(self):
        self.assertEqual(run("--top", "2"), "    4  the\n    2  cat\n")


if __name__ == "__main__":
    unittest.main()
