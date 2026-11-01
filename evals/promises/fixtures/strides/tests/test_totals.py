import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from strides.__main__ import main

LOG = """\
2026-03-02 06:40 5.0 Ada Lim
2026-03-02 18:05 3.2 Ben Okafor
# tablet restarted
2026-03-03 07:10 4.1 Ada Lim

"""


class TotalsTest(unittest.TestCase):
    def test_kilometres_per_member_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "club.log"
            path.write_text(LOG, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                main(["totals", str(path)])
        self.assertEqual(out.getvalue(), "Ada Lim: 9.1 km\nBen Okafor: 3.2 km\n")


if __name__ == "__main__":
    unittest.main()
