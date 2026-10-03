import unittest

from render import Row, clip, line_count, render_group


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            Row("2026-03-01T08:00", "first"),
            Row("2026-03-01T10:00", "second"),
        ]

    def test_header_names_the_tag_and_count(self):
        block = render_group("ops", self.rows)
        self.assertEqual(block.text.splitlines()[0], "== ops (2) ==")

    def test_columns_are_two_spaces_apart(self):
        block = render_group("ops", self.rows)
        self.assertEqual(block.text.splitlines()[1], "2026-03-01T08:00  first")

    def test_block_ends_with_a_newline(self):
        self.assertTrue(render_group("ops", self.rows).text.endswith("\n"))

    def test_clip_shortens_long_text(self):
        self.assertEqual(clip("abcdefghij", 8), "abcde...")

    def test_line_count_includes_the_header(self):
        self.assertEqual(line_count(render_group("ops", self.rows)), 3)


if __name__ == "__main__":
    unittest.main()
