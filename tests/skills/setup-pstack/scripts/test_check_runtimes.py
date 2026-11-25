import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "skills" / "setup-pstack" / "scripts" / "check-runtimes.sh"
BASH = shutil.which("bash")


def tool(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def python_reporting(version: tuple[int, int, int]) -> str:
    """A stand-in python3 that answers the two questions the script asks of it."""
    dotted = ".".join(str(part) for part in version)
    supported = 0 if version >= (3, 9, 0) else 1
    return f'case "$2" in *print*) echo {dotted} ;; *) exit {supported} ;; esac\n'


@unittest.skipUnless(BASH, "bash is not installed")
class CheckRuntimes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def run_script(self):
        result = subprocess.run([BASH, str(SCRIPT)], capture_output=True, text=True, env={"PATH": str(self.bin)})
        lines = dict(line.split(": ", 1) for line in result.stdout.splitlines())
        return result.returncode, lines

    def test_every_runtime_present_exits_zero(self):
        tool(self.bin, "python3", python_reporting((3, 12, 4)))
        for name in ("bun", "node", "gh"):
            tool(self.bin, name, "exit 0\n")
        code, lines = self.run_script()
        self.assertEqual(code, 0)
        self.assertEqual(lines, {"python3": "3.12.4", "bun": "found", "node": "found", "gh": "found"})

    def test_missing_python_is_the_only_fatal_gap(self):
        code, lines = self.run_script()
        self.assertEqual(code, 1)
        self.assertEqual(set(lines), {"python3", "bun", "node", "gh"})
        for name in lines:
            self.assertTrue(lines[name].startswith("missing. "), lines[name])

    def test_missing_optional_tools_are_reported_and_not_fatal(self):
        tool(self.bin, "python3", python_reporting((3, 9, 0)))
        code, lines = self.run_script()
        self.assertEqual(code, 0)
        self.assertEqual(lines["python3"], "3.9.0")
        self.assertEqual(lines["node"], "missing. The statechart launcher can use bun or Deno 2.0 or newer.")
        for name in ("bun", "gh"):
            self.assertTrue(lines[name].startswith("missing. Stops: "), lines[name])

    def test_python_older_than_3_9_is_fatal(self):
        tool(self.bin, "python3", python_reporting((3, 8, 18)))
        code, lines = self.run_script()
        self.assertEqual(code, 1)
        self.assertTrue(lines["python3"].startswith("3.8.18 is older than 3.9. "), lines["python3"])

    def test_python_that_does_not_run_is_fatal(self):
        tool(self.bin, "python3", "exit 1\n")
        code, lines = self.run_script()
        self.assertEqual(code, 1)
        self.assertTrue(lines["python3"].startswith("found but does not run. "), lines["python3"])


if __name__ == "__main__":
    unittest.main()
