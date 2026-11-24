import unittest
from collections import Counter

from tally.report import plain_report


class Report(unittest.TestCase):
    def test_rows_follow_the_counts(self):
        self.assertEqual(plain_report(Counter({"the": 3, "cat": 1}), 2), "    3  the\n    1  cat")


if __name__ == "__main__":
    unittest.main()
