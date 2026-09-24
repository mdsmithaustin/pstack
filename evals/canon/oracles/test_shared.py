import unittest

from check import grade
from shared import parse_files


class AnswerParsingTests(unittest.TestCase):
    def test_fenced_file_body_is_unwrapped(self):
        files = parse_files('<file path="a.py">\n```python\nx = 1\n```\n</file>')
        self.assertEqual(files, {"a.py": "x = 1\n"})

    def test_path_outside_the_project_is_refused(self):
        self.assertEqual(
            grade("fork-shared-helper", "payroll-overtime", text='<file path="../escape.py">\nx = 1\n</file>'),
            ["unsafe file path in answer: '../escape.py'"],
        )
