import unittest

from roster.report import count_by_team

ROWS = [
    {"name": "ada", "team": "infra"},
    {"name": "bob", "team": "web"},
    {"name": "cy", "team": "infra"},
]


class CountByTeamTest(unittest.TestCase):
    def test_counts_sorted_by_team(self):
        self.assertEqual(count_by_team(ROWS), [("infra", 2), ("web", 1)])
