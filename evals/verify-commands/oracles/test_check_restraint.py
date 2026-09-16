from __future__ import annotations

import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("check_restraint", ROOT / "check_restraint.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CheckRestraintTests(unittest.TestCase):
    def write_output(self, text: str) -> Path:
        directory = Path(self.addCleanupDirectory()).resolve()
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

    def test_rejects_a_symlinked_output_file(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        target = directory / "candidate.md"
        target.write_text("safe", encoding="utf-8")
        (directory / "output.md").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "contains a symlink"):
            MODULE.read_output(directory)

    def test_rejects_output_below_a_symlinked_ancestor(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        real = directory / "real"
        real.mkdir()
        (real / "output.md").write_text("safe", encoding="utf-8")
        alias = directory / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "contains a symlink"):
            MODULE.read_output(alias)

    def test_rejects_a_non_regular_output_file(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        (directory / "output.md").mkdir()
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            MODULE.read_output(directory)

    def test_reads_from_the_standard_unresolved_temporary_root(self) -> None:
        directory = Path(self.addCleanupDirectory())
        (directory / "output.md").write_text("safe", encoding="utf-8")
        self.assertEqual(MODULE.read_output(directory), "safe")

    def test_rejects_a_hard_linked_output_file(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        target = directory / "external.md"
        target.write_text("safe", encoding="utf-8")
        os.link(target, directory / "output.md")
        with self.assertRaisesRegex(MODULE.InfrastructureFailure, "exactly one hard link"):
            MODULE.read_output(directory)

    def test_main_labels_untrusted_output_as_infrastructure(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        target = directory / "candidate.md"
        target.write_text("safe", encoding="utf-8")
        (directory / "output.md").symlink_to(target)
        stdout = io.StringIO()
        with mock.patch("sys.argv", ["check_restraint.py", "pipefail", str(directory)]), mock.patch(
            "sys.stdout", stdout
        ):
            code = MODULE.main()
        self.assertEqual(code, 2)
        self.assertIn("INFRASTRUCTURE_FAILURE", stdout.getvalue())

    def test_rejects_output_swapped_to_a_symlink_at_open(self) -> None:
        directory = Path(self.addCleanupDirectory()).resolve()
        output = directory / "output.md"
        output.write_text("safe", encoding="utf-8")
        target = directory / "replacement.md"
        target.write_text("unsafe", encoding="utf-8")
        real_open = MODULE.os.open
        swapped = False

        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "output.md" and not swapped:
                swapped = True
                output.unlink()
                output.symlink_to(target)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(MODULE.os, "open", side_effect=swap_then_open):
            with self.assertRaisesRegex(MODULE.InfrastructureFailure, "contains a symlink"):
                MODULE.read_output(directory)
        self.assertTrue(swapped)


if __name__ == "__main__":
    unittest.main()
