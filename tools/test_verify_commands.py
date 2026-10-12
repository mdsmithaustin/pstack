import re
import shutil
import subprocess
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "verify-commands" / "SKILL.md"
TRAP_ROW = re.compile(r"^\| `[^|\n]*\\\| tail.*$", re.M)
CODE_SPAN = re.compile(r"`([^`]+)`")
SHELL_NAME = re.compile(r"\b(?:bash|zsh|dash|ksh|sh)\b")
PIPEFAIL_ONE_LINER = re.compile(r"^set -[a-z]*o pipefail; .+\| tail\b")


def run(shell, script):
    done = subprocess.run([shell, "-c", script], capture_output=True, text=True, check=False)
    return done.returncode, done.stdout.strip()


def read_trap_row():
    match = TRAP_ROW.search(SKILL.read_text(encoding="utf-8"))
    return match.group(0) if match else None


def remedy_and_shells(row):
    spans = [span.replace("\\|", "|") for span in CODE_SPAN.findall(row)]
    remedy = next((span for span in spans if PIPEFAIL_ONE_LINER.match(span)), None)
    shells = sorted(set(SHELL_NAME.findall(CODE_SPAN.sub("", row))))
    return remedy, shells


class ProducerExitStatus(unittest.TestCase):
    def test_trap_row_remedy_surfaces_a_failing_producer_in_every_shell_it_names(self):
        row = read_trap_row()
        self.assertIsNotNone(row, "the trap table needs a row for a verdict read off `cmd | tail`")
        remedy, shells = remedy_and_shells(row)
        self.assertIsNotNone(
            remedy, "the trap row needs a one-line `set -o pipefail; cmd | tail` remedy in one code span"
        )
        self.assertTrue(shells, "the trap row must name the shells its remedy covers")
        pipeline = remedy.split(";", 1)[1]
        producer = pipeline.split("|")[0].split()[0]
        failing_producer = f"{producer}() {{ echo boom; return 1; }}"
        for shell in shells:
            with self.subTest(shell=shell):
                if shutil.which(shell) is None:
                    self.skipTest(f"{shell} is not installed")
                self.assertEqual(run(shell, f"{failing_producer}; {pipeline}")[0], 0, "control: tail masks the failure")
                self.assertEqual(run(shell, f"{failing_producer}; {remedy}")[0], 1)


if __name__ == "__main__":
    unittest.main()
