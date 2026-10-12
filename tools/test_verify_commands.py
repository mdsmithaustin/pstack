import re
import shutil
import subprocess
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "verify-commands" / "SKILL.md"
TRAP_ROW = re.compile(r"^\| `[^|\n]*\\\| tail.*$", re.M)
CODE_SPAN = re.compile(r"`([^`]+)`")


def run(shell, script):
    done = subprocess.run([shell, "-c", script], capture_output=True, text=True, check=False)
    return done.returncode, done.stdout.strip()


def remedies_in_trap_row():
    match = TRAP_ROW.search(SKILL.read_text(encoding="utf-8"))
    if match is None:
        return {}
    spans = CODE_SPAN.findall(match.group(0))
    return {
        "pipefail": next((s for s in spans if s.startswith("set -o pipefail")), None),
        "pipestatus": next((s for s in spans if "PIPESTATUS" in s), None),
    }


class ProducerExitStatus(unittest.TestCase):
    def test_a_pipeline_reports_its_last_command(self):
        self.assertEqual(run("bash", "false | tail -1"), (0, ""))

    def test_trap_table_remedies_surface_a_failing_producer(self):
        remedies = remedies_in_trap_row()
        self.assertTrue(remedies, "the trap table needs a row for a verdict read off `cmd | tail`")
        self.assertIsNotNone(remedies["pipefail"])
        self.assertIsNotNone(remedies["pipestatus"])
        for shell in ("bash", "zsh"):
            if shutil.which(shell) is None:
                continue
            with self.subTest(remedy="pipefail", shell=shell):
                script = f"{remedies['pipefail']}; false | tail -1; echo $?"
                self.assertEqual(run(shell, script), (0, "1"))
        with self.subTest(remedy="pipestatus", shell="bash"):
            script = f"false | tail -1; echo {remedies['pipestatus']}"
            self.assertEqual(run("bash", script), (0, "1"))


if __name__ == "__main__":
    unittest.main()
