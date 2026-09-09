#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstalledPersonaRegression(unittest.TestCase):
    def test_copied_skills_deliver_both_complete_personas(self):
        with tempfile.TemporaryDirectory(prefix="pstack-copied-personas-") as temporary:
            installed = Path(temporary) / "installed skills"
            shutil.copytree(ROOT / "skills", installed)
            command = installed / "pstack-harness/scripts/subagents.py"
            for alias, source in (
                ("poteto-agent", "poteto-agent.md"),
                ("Comment Sicko", "comment-sicko.md"),
            ):
                with self.subTest(alias=alias):
                    result = subprocess.run(
                        [sys.executable, str(command), "brief", alias],
                        cwd=temporary, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    body = (ROOT / "agents" / source).read_text().split("---\n", 2)[2]
                    self.assertIn(body, result.stdout)
                    self.assertIn(str(installed), result.stdout)
                    self.assertNotIn(str(ROOT), result.stdout)


if __name__ == "__main__":
    unittest.main()
