from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("check_restraint", ROOT / "check_restraint.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CheckRestraintTests(unittest.TestCase):
    def write_output(self, text: str) -> Path:
        directory = Path(self.addCleanupDirectory())
        (directory / "output.md").write_text(text, encoding="utf-8")
        return directory

    def addCleanupDirectory(self) -> str:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return temporary.name

    def test_accepts_brief_pipefail_explanation(self) -> None:
        text = "`set -o pipefail` makes a pipeline return non-zero when an earlier command fails, even if the last command succeeds."
        MODULE.check_pipefail(MODULE.read_output(self.write_output(text)))

    def test_accepts_exact_formatted_command(self) -> None:
        text = "```sh\ndocker ps --format '{{.Names}}'\n```\n\nIt prints container names."
        MODULE.check_format_command(MODULE.read_output(self.write_output(text)))

    def test_rejects_changed_formatted_command(self) -> None:
        text = "```sh\ndocker ps --format '{{.ID}}'\n```\n\nIt prints container IDs."
        with self.assertRaisesRegex(ValueError, "exact command"):
            MODULE.check_format_command(MODULE.read_output(self.write_output(text)))


if __name__ == "__main__":
    unittest.main()
