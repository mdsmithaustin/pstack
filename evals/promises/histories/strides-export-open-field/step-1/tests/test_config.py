import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from strides.__main__ import main

LOG = """\
2026-03-02 06:40 5.0 Ada Lim
2026-03-02 18:05 3.2 Ben Okafor
2026-03-03 07:10 4.1 Ada Lim
"""


class ConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "runs.txt").write_text(LOG, encoding="utf-8")

    def totals(self, config_text):
        (self.dir / "club.conf").write_text(config_text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["totals", "--config", str(self.dir / "club.conf")])
        return code, out.getvalue(), err.getvalue()

    def test_the_log_comes_from_the_config_relative_to_its_folder(self):
        code, out, _ = self.totals("# club settings\n\nlog: log://runs.txt\n")
        self.assertEqual((code, out), (0, "Ada Lim: 9.1 km\nBen Okafor: 3.2 km\n"))

    def test_a_log_value_without_the_log_scheme_exits_2(self):
        code, out, err = self.totals("log: runs.txt\n")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("log must start with log://", err)

    def test_an_unknown_key_exits_2(self):
        code, out, err = self.totals("log: log://runs.txt\ncolour: blue\n")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("unknown key colour", err)


if __name__ == "__main__":
    unittest.main()
