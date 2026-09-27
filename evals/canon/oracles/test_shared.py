import unittest

from check import RULES, grade
from shared import parse_files


class AnswerParsingTests(unittest.TestCase):
    def test_fenced_file_body_is_unwrapped(self):
        files = parse_files('<file path="a.py">\n```python\nx = 1\n```\n</file>')
        self.assertEqual(files, {"a.py": "x = 1\n"})

    def test_path_outside_the_project_is_refused(self):
        self.assertEqual(
            grade("value-type", "marketplace-subtotal", text='<file path="../escape.py">\nx = 1\n</file>'),
            ["unsafe file path in answer: '../escape.py'"],
        )


class ProbeOutputTests(unittest.TestCase):
    def test_answer_that_prints_at_import_fails_instead_of_crashing_the_grader(self):
        good = (RULES / "value-type" / "cases" / "marketplace-subtotal" / "samples" / "good.md").read_text()
        noisy = good.replace('<file path="checkout/money.py">\n', '<file path="checkout/money.py">\nprint("loading money")\n')

        self.assertEqual(grade("value-type", "marketplace-subtotal", text=good), [])
        self.assertEqual(
            grade("value-type", "marketplace-subtotal", text=noisy),
            ["the probe output is not JSON: Expecting value: line 1 column 1 (char 0)"],
        )
