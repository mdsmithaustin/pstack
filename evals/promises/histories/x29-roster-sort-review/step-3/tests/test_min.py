import unittest

from roster.report import drop_small


class DropSmallTest(unittest.TestCase):
    def test_drops_teams_below_the_minimum(self):
        self.assertEqual(drop_small([("infra", 3), ("web", 2)], 3), [("infra", 3)])
