import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from check import RULES, grade
import shared
from shared import PROJECT_IMAGES, OracleError, parse_files, plain_test_failures, project_test_results, run_jobs


class AnswerParsingTests(unittest.TestCase):
    def test_fenced_file_body_is_unwrapped(self):
        files = parse_files('<file path="a.py">\n```python\nx = 1\n```\n</file>')
        self.assertEqual(files, {"a.py": "x = 1\n"})

    def test_path_outside_the_project_is_refused(self):
        self.assertEqual(
            grade("value-type", "marketplace-subtotal", text='<file path="../escape.py">\nx = 1\n</file>'),
            ["unsafe file path in answer: '../escape.py'"],
        )


class DocumentTextTests(unittest.TestCase):
    FILE = {"file": "ops/premortem.md"}
    ANSWER = ('Here is a draft.\n<file path="ops/premortem.md">\n# Draft\n</file>\n'
              'Revised:\n<file path="ops/premortem.md">\n```markdown\n# Premortem\n\nGIT_DIR leaks into the fixtures.\n```\n</file>\nDone.\n')

    def test_the_last_block_for_the_path_wins_with_its_fence_stripped(self):
        self.assertEqual(shared.document_text(self.ANSWER, self.FILE), "# Premortem\n\nGIT_DIR leaks into the fixtures.\n")

    def test_a_missing_block_is_an_empty_document_and_the_message_form_is_the_whole_answer(self):
        self.assertEqual(shared.document_text('<file path="ops/other.md">\nx\n</file>\n', self.FILE), "")
        self.assertEqual(shared.document_text("", self.FILE), "")
        self.assertEqual(shared.document_text(self.ANSWER, {"message": True}), self.ANSWER)

    def test_an_unsafe_path_in_another_block_does_not_hide_the_document(self):
        answer = '<file path="../escape.py">\nx = 1\n</file>\n<file path="./ops/premortem.md">\n# Premortem\n</file>\n'
        self.assertEqual(shared.document_text(answer, self.FILE), "# Premortem\n")

    def test_a_workspace_document_is_the_file_after_the_diff(self):
        diff = ("diff --git a/ops/premortem.md b/ops/premortem.md\nnew file mode 100644\n--- /dev/null\n+++ b/ops/premortem.md\n"
                "@@ -0,0 +1 @@\n+# Premortem\n")
        deletion = "diff --git a/ops/proposal.md b/ops/proposal.md\ndeleted file mode 100644\n--- a/ops/proposal.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-# Proposal\n"
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / "ops").mkdir()
            (checkout / "ops" / "proposal.md").write_text("# Proposal\n")
            self.assertEqual(shared.document_text("Done.", self.FILE, shared.Workspace(checkout, diff)), "# Premortem\n")
            self.assertEqual(shared.document_text("Done.", self.FILE, shared.Workspace(checkout, "")), "")
            self.assertEqual(shared.document_text("Done.", {"file": "ops/proposal.md"}, shared.Workspace(checkout, "")), "# Proposal\n")
            self.assertEqual(shared.document_text("Done.", {"file": "ops/proposal.md"}, shared.Workspace(checkout, deletion)), "")


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


def built_image(name):
    images = json.loads(PROJECT_IMAGES.read_text()) if PROJECT_IMAGES.is_file() else {}
    try:
        found = name in images and subprocess.run(["docker", "image", "inspect", images[name]["id"]],
                                                  capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        found = False
    if not found:
        raise unittest.SkipTest(f"needs the {name} image; build it with images/build.py")
    return name


class ProjectImageTests(unittest.TestCase):
    def test_unknown_image_is_refused(self):
        with self.assertRaisesRegex(OracleError, "no dependency image 'nothing-here'"):
            project_test_results("nothing-here", Path("."), {}, ["tests/test_calc.py"])


class ProjectTestTimeoutTests(unittest.TestCase):
    def test_a_timed_out_run_kills_its_container_and_raises_oracle_error(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory) / "images.json"
            images.write_text(json.dumps({"calc": {"id": "sha256:feed"}}))
            with mock.patch.object(shared, "PROJECT_IMAGES", images), mock.patch.object(shared.subprocess, "run", fake_run):
                with self.assertRaisesRegex(OracleError, "project tests timed out after 900s"):
                    project_test_results("calc", Path(directory), {}, ["tests/test_calc.py"])

        name = calls[0][calls[0].index("--name") + 1]
        self.assertEqual(calls[1], ["docker", "kill", name])


class ProjectTestRunnerTests(unittest.TestCase):
    CHECKOUT = {
        "calc.py": "def double(x):\n    return x * 3\n",
        "tests/test_calc.py": (
            "import socket\nimport pytest\nfrom calc import double\n\n"
            "def test_zero():\n    assert double(0) == 0\n\n"
            "def test_two():\n    assert double(2) == 4\n\n"
            "@pytest.mark.skip\ndef test_later():\n    pass\n\n"
            "def test_network():\n    socket.create_connection((\"1.1.1.1\", 53), timeout=5)\n"
        ),
        "web/package.json": "{}\n",
        "web/src/calc.test.ts": "import { expect, test } from 'vitest'\n\ntest('adds', () => { expect(1 + 1).toBe(2) })\n",
    }

    def setUp(self):
        self.image = built_image("omnigent-336207801509")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.checkout = Path(directory.name)
        for path, body in self.CHECKOUT.items():
            (self.checkout / path).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / path).write_text(body)

    def test_outcomes_are_named_per_test_and_the_network_is_off(self):
        self.assertEqual(
            project_test_results(self.image, self.checkout, {}, ["tests/test_calc.py", "web/src/calc.test.ts"]),
            {"tests.test_calc::test_zero": "passed", "tests.test_calc::test_two": "failed",
             "tests.test_calc::test_later": "skipped", "tests.test_calc::test_network": "failed",
             "web/src/calc.test.ts::adds": "passed"},
        )

    def test_diff_files_replace_and_delete_checkout_files_in_a_copy(self):
        fixed = {"calc.py": b"def double(x):\n    return x * 2\n", "tests/test_calc.py": None}
        self.assertEqual(
            project_test_results(self.image, self.checkout, fixed, ["tests/test_calc.py"]),
            {"tests/test_calc.py": "failed"},
        )
        self.assertEqual(
            project_test_results(self.image, self.checkout, {"calc.py": fixed["calc.py"]}, ["tests/test_calc.py::test_two"]),
            {"tests.test_calc::test_two": "passed"},
        )
        self.assertEqual((self.checkout / "calc.py").read_text(), self.CHECKOUT["calc.py"])
