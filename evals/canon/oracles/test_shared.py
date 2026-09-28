import unittest

from check import RULES, grade
from shared import parse_files, plain_test_failures, run_jobs


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


class ContainerJobTests(unittest.TestCase):
    def test_job_sees_only_its_own_tree(self):
        trees = {"amended": {"a.py": "x = 1\n"}, "current": {"b.py": "y = 2\n"}}
        listing = ["python3", "-c", "import os; print(sorted(os.listdir('/work')), sorted(os.listdir('.')))"]

        results = run_jobs(trees, [{"tree": "current", "argv": listing}, {"tree": "amended", "argv": listing}])

        self.assertEqual(
            [result["stdout"] for result in results],
            ["['current'] ['b.py']\n", "['amended'] ['a.py']\n"],
        )

    def test_job_cannot_plant_the_next_jobs_directory(self):
        trees = {"current": {"a.py": "x = 1\n"}}
        plant = ["python3", "-c", "import os; os.makedirs('/tmp/job-1/planted'); print('planted')"]
        listing = ["python3", "-c", "import os; print(sorted(os.listdir('.')))"]

        results = run_jobs(trees, [{"tree": "current", "argv": plant}, {"tree": "current", "argv": listing}])

        self.assertEqual([result["stdout"] for result in results], ["planted\n", "['a.py']\n"])


class PlainTestRunnerTests(unittest.TestCase):
    TREE = {
        "pkg/__init__.py": "",
        "pkg/calc.py": "def double(x):\n    return x * 3\n",
        "tests/__init__.py": "",
        "tests/test_calc.py": (
            "from pkg.calc import double\nprint(\"loaded\")\n\n"
            "def test_zero():\n    assert double(0) == 0\n\n"
            "def test_two():\n    assert double(2) == 4\n\n"
            "def helper(value):\n    assert value\n\n"
            "class TestCalc:\n"
            "    def setup_method(self):\n        self.base = 1\n\n"
            "    def test_one(self):\n        assert double(self.base) == 2\n\n"
            "    def test_negative(self):\n        assert double(-self.base) == -3\n"
        ),
    }

    def test_failing_functions_and_methods_are_named(self):
        self.assertEqual(
            plain_test_failures(self.TREE, ["tests.test_calc"]),
            ["tests.test_calc::test_two failed", "tests.test_calc::TestCalc::test_one failed"],
        )

    def test_module_that_does_not_import_is_one_failure(self):
        tree = {**self.TREE, "pkg/calc.py": "def double(x) return x\n"}
        self.assertEqual(plain_test_failures(tree, ["tests.test_calc"]), ["tests.test_calc does not import: SyntaxError"])

    def test_module_with_no_tests_is_a_failure(self):
        tree = {**self.TREE, "tests/test_calc.py": "X = 1\n"}
        self.assertEqual(plain_test_failures(tree, ["tests.test_calc"]), ["tests.test_calc holds no test functions"])
