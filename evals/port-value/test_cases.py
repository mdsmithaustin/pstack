import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CASES = Path(__file__).resolve().parent / "cases"
COUNTS = {
    "parcel-manifest": {"initial": 16, "maintenance": 26},
    "meter-intervals": {"initial": 18, "maintenance": 28},
    "retention-schedule": {"initial": 17, "maintenance": 29},
}


class CaseControls(unittest.TestCase):
    def setUp(self):
        self.cases = {
            directory.name: (directory, json.loads((directory / "case.json").read_text()))
            for directory in CASES.iterdir() if directory.is_dir()
        }
        self.assertEqual(set(self.cases), set(COUNTS))

    def run_oracle(self, name, project, stage, passed):
        directory, metadata = self.cases[name]
        completed = subprocess.run(
            [sys.executable, str(directory / metadata["oracle"]),
             "--project", str(project), "--stage", stage],
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0 if passed else 1, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(set(result), {"passed", "assertions", "failures"})
        self.assertIs(result["passed"], passed)
        self.assertEqual(result["assertions"], COUNTS[name][stage])
        self.assertGreater(result["assertions"], 0)
        self.assertIsInstance(result["failures"], list)
        if passed:
            self.assertEqual(result["failures"], [])
        else:
            self.assertGreater(len(result["failures"]), 0)
        return result

    def test_initial_controls_pass_initial_contract(self):
        for name, (directory, metadata) in self.cases.items():
            with self.subTest(case=name):
                self.run_oracle(name, directory / metadata["controls"]["initial"], "initial", True)

    def test_maintenance_controls_preserve_both_contracts(self):
        for name, (directory, metadata) in self.cases.items():
            project = directory / metadata["controls"]["maintenance"]
            for stage in ("initial", "maintenance"):
                with self.subTest(case=name, stage=stage):
                    self.run_oracle(name, project, stage, True)

    def test_initial_controls_fail_new_maintenance_behavior(self):
        for name, (directory, metadata) in self.cases.items():
            with self.subTest(case=name):
                self.run_oracle(name, directory / metadata["controls"]["initial"], "maintenance", False)

    def test_starters_and_noops_fail_both_stages(self):
        for name, (directory, metadata) in self.cases.items():
            for path in (metadata["project"], metadata["controls"]["noop"]):
                for stage in ("initial", "maintenance"):
                    with self.subTest(case=name, path=path, stage=stage):
                        self.run_oracle(name, directory / path, stage, False)

    def test_targeted_maintenance_controls_preserve_initial_behavior(self):
        for name, (directory, metadata) in self.cases.items():
            with self.subTest(case=name):
                project = directory / metadata["controls"]["targeted"]
                self.run_oracle(name, project, "initial", True)
                self.run_oracle(name, project, "maintenance", False)

    def test_each_defect_fails_its_named_check(self):
        for name, (directory, metadata) in self.cases.items():
            for defect in metadata["defects"]:
                with self.subTest(case=name, defect=defect["path"]):
                    result = self.run_oracle(name, directory / defect["path"], defect["stage"], False)
                    self.assertTrue(any(
                        failure.startswith(defect["failure"] + ":")
                        for failure in result["failures"]
                    ), result)

    def test_numeric_output_types_are_exact(self):
        examples = {
            "parcel-manifest": ({"consignments": [], "total_grams": False}, "empty manifest"),
            "meter-intervals": ({"intervals": [], "total_usage": False}, "empty readings"),
        }
        for name, (output, failure_name) in examples.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                (project / "app.py").write_text("print(" + repr(json.dumps(output)) + ")\n")
                result = self.run_oracle(name, project, "initial", False)
                self.assertTrue(any(
                    failure.startswith(failure_name + ":") for failure in result["failures"]
                ), result)

    def test_oracles_run_outside_the_case_and_reject_protocol_errors(self):
        for name, (directory, metadata) in self.cases.items():
            with tempfile.TemporaryDirectory() as temporary:
                copied = Path(temporary) / "private"
                shutil.copytree(directory, copied)
                project = Path(temporary) / "application"
                shutil.copytree(copied / metadata["controls"]["maintenance"], project)
                completed = subprocess.run(
                    [sys.executable, str(copied / metadata["oracle"]),
                     "--project", str(project), "--stage", "maintenance"],
                    cwd=temporary, text=True, capture_output=True, timeout=30,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(json.loads(completed.stdout), {
                    "passed": True, "assertions": COUNTS[name]["maintenance"], "failures": [],
                })
                (project / "app.py").write_text('print("{}")\nprint("extra output")\n')
                self.run_oracle(name, project, "initial", False)
                (project / "app.py").write_text('raise SystemExit(7)\n')
                self.run_oracle(name, project, "initial", False)
                (project / "app.py").unlink()
                self.run_oracle(name, project, "initial", False)


if __name__ == "__main__":
    unittest.main()
