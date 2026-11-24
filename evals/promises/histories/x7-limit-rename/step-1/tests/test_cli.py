import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tally.__main__ import main


def run(*args, text="the cat sat on the mat\nthe dog sat on the log\na cat and a dog\n"):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "in.txt"
        path.write_text(text, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(path), *args])
    return out.getvalue()


class Cli(unittest.TestCase):
    def test_top_limits_the_rows(self):
        self.assertEqual(run("--top", "2"), "    4  the\n    2  cat\n")

    def test_default_prints_five_rows(self):
        self.assertEqual(len(run().splitlines()), 5)


if __name__ == "__main__":
    unittest.main()
