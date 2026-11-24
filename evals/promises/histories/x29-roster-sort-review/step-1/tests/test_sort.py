import unittest

from roster.report import sort_counts

PAIRS = [("infra", 3), ("ops", 3), ("web", 2), ("data", 5)]


class SortCountsTest(unittest.TestCase):
    def test_count_puts_biggest_first_and_breaks_ties_by_team(self):
        self.assertEqual(sort_counts(PAIRS, "count"), [("data", 5), ("infra", 3), ("ops", 3), ("web", 2)])

    def test_team_keeps_the_order_it_was_given(self):
        self.assertEqual(sort_counts(PAIRS, "team"), PAIRS)
