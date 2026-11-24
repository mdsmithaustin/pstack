import unittest

from roster.report import top_teams

ROWS = [
    {"name": "ada", "team": "infra"},
    {"name": "bob", "team": "web"},
    {"name": "cy", "team": "infra"},
    {"name": "dee", "team": "data"},
    {"name": "eli", "team": "web"},
    {"name": "fay", "team": "infra"},
]


class TopTeamsTest(unittest.TestCase):
    def test_largest_first(self):
        self.assertEqual(top_teams(ROWS, 1), [("infra", 3)])

    def test_cut_to_n(self):
        self.assertEqual(len(top_teams(ROWS, 2)), 2)

    def test_n_larger_than_team_count(self):
        self.assertEqual(top_teams(ROWS, 10), [("infra", 3), ("web", 2), ("data", 1)])


if __name__ == "__main__":
    unittest.main()
