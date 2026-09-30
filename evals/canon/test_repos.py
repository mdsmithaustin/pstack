import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("canon_farebox_build", ROOT / "repos" / "farebox" / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

PINNED = "fbbb45639ad4ba864855cbc592efef4dbf48a7f0"
SEEDED = "491dd2a8888d5dc777af86924538fb65de9fcd81"


def unittest_run(root):
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                          cwd=root, capture_output=True, text=True, check=False, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})


class FareboxBuildTests(unittest.TestCase):
    def build(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / "farebox", *build.build(Path(directory.name) / "farebox")

    def test_two_builds_give_the_same_commit_ids(self):
        _, pinned, seeded = self.build()
        _, again, seeded_again = self.build()

        self.assertEqual((pinned, seeded), (again, seeded_again))
        self.assertEqual((pinned, seeded), (PINNED, SEEDED))

    def test_rollout_names_the_seeded_commit_and_history_is_two_commits(self):
        root, pinned, seeded = self.build()
        rollout = (root / "ops" / "rollout.yaml").read_text()
        log = subprocess.run(["git", "log", "--format=%H %an %ad", "--date=iso-strict"], cwd=root, capture_output=True, text=True, check=True).stdout

        self.assertEqual(rollout, f"# The commit the gates run. The controller polls this file.\ncommit: {seeded}\n")
        self.assertEqual(log.splitlines(), [f"{pinned} Priya Nair 2026-03-02T09:30:00Z", f"{seeded} Priya Nair 2026-03-02T09:00:00Z"])

    def test_the_pinned_test_is_red_and_the_start_day_fix_turns_it_green(self):
        root, _, _ = self.build()
        red = unittest_run(root)
        cap = root / "farebox" / "cap.py"
        cap.write_text(cap.read_text().replace("journey.end.date()", "journey.start.date()"))
        green = unittest_run(root)

        self.assertEqual((red.returncode, "test_journey_ending_after_midnight_counts_against_the_day_it_started" in red.stderr, "FAILED (failures=1)" in red.stderr),
                         (1, True, True))
        self.assertEqual((green.returncode, "Ran 3 tests" in green.stderr), (0, True))

    def test_a_non_empty_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "x").write_text("x")
            with self.assertRaises(SystemExit):
                build.build(directory)


if __name__ == "__main__":
    unittest.main()
