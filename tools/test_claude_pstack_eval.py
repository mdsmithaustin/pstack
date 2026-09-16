from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "tools" / "claude-pstack-eval"


@unittest.skipUnless(platform.system() == "Darwin", "requires macOS sandbox-exec")
class ClaudePstackEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        (self.workspace / "inputs").mkdir(parents=True)
        (self.workspace / "skills").mkdir()
        (self.workspace / "inputs" / "fixture.txt").write_text("input\n", encoding="utf-8")
        (self.workspace / "skills" / "SKILL.md").write_text("skill\n", encoding="utf-8")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "claude"
        fake.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "touch scratch-ok\n"
            "if touch inputs/changed 2>/dev/null; then exit 91; fi\n"
            "if touch skills/changed 2>/dev/null; then exit 92; fi\n"
            "printf '%s\\n' \"$@\" > received-args\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

    def run_wrapper(self, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        return subprocess.run(
            [str(WRAPPER), "--model", "opus"],
            cwd=cwd or self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_allows_scratch_but_protects_inputs_and_skills(self) -> None:
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.workspace / "scratch-ok").is_file())
        self.assertFalse((self.workspace / "inputs" / "changed").exists())
        self.assertFalse((self.workspace / "skills" / "changed").exists())
        self.assertEqual(
            (self.workspace / "received-args").read_text(encoding="utf-8").splitlines(),
            [
                "--setting-sources",
                "project",
                "--permission-mode",
                "bypassPermissions",
                "--model",
                "opus",
            ],
        )

    def test_fails_closed_outside_a_harness_workspace(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        result = self.run_wrapper(empty)
        self.assertEqual(result.returncode, 126)
        self.assertIn("no inputs directory", result.stderr)

    def test_allows_a_control_arm_without_a_skills_directory(self) -> None:
        (self.workspace / "skills" / "SKILL.md").unlink()
        (self.workspace / "skills").rmdir()
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.workspace / "scratch-ok").is_file())
        self.assertFalse((self.workspace / "inputs" / "changed").exists())


if __name__ == "__main__":
    unittest.main()
