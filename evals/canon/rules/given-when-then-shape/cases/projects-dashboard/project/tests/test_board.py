import unittest

from projects import Board


class BoardTest(unittest.TestCase):
    def test_project_lifecycle(self):
        board = Board()
        apollo = board.create_project("Apollo")
        self.assertEqual(board.dashboard(), ["Apollo"])
        board.create_project("Gemini")
        self.assertEqual(board.dashboard(), ["Apollo", "Gemini"])
        board.rename_project(apollo.id, "Artemis")
        self.assertEqual(board.dashboard(), ["Artemis", "Gemini"])


if __name__ == "__main__":
    unittest.main()
