import unittest

from tally.fmt import format_line


class Fmt(unittest.TestCase):
    def test_count_is_right_aligned(self):
        self.assertEqual(format_line("cat", 2), "    2  cat")

    def test_w(self):
        self.assertEqual(format_line("cat", 2, width=3), "  2  cat")


if __name__ == "__main__":
    unittest.main()
