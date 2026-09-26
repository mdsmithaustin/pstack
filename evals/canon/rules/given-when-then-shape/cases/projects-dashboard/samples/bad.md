Following the lifecycle test's style:

<file path="tests/test_board.py">
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

    def test_archive_project(self):
        # Given two projects
        board = Board()
        apollo = board.create_project("Apollo")
        board.create_project("Gemini")
        self.assertEqual(board.dashboard(), ["Apollo", "Gemini"])
        # When one is archived
        board.archive_project(apollo.id)
        # Then only the other is shown
        self.assertEqual(board.dashboard(), ["Gemini"])


if __name__ == "__main__":
    unittest.main()
</file>
