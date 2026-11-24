import unittest

from tally.fmt import format_row


class Fmt(unittest.TestCase):
    def test_count_is_right_aligned(self):
        self.assertEqual(format_row("cat", 2), "    2  cat")


if __name__ == "__main__":
    unittest.main()
