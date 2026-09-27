The new test archives one of two projects and checks what the dashboard still lists.

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

    def test_archived_project_leaves_the_dashboard(self):
        board = Board()
        apollo = board.create_project("Apollo")
        board.create_project("Gemini")

        board.archive_project(apollo.id)

        self.assertEqual(board.dashboard(), ["Gemini"])


if __name__ == "__main__":
    unittest.main()
</file>
