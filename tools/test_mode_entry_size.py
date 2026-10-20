import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).with_name("check-mode-entry-size.py")


class ModeEntryBudget(unittest.TestCase):
    def test_repository_mode_entries_meet_the_policy(self):
        result = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS mode entry: skills/poteto-mode/SKILL.md:", result.stdout)

    def check_entry(self, content):
        with tempfile.TemporaryDirectory() as directory:
            entry = Path(directory) / "skills/poteto-mode/SKILL.md"
            if content is not None:
                entry.parent.mkdir(parents=True)
                entry.write_bytes(content)
            return subprocess.run(
                [sys.executable, str(CHECKER), "--root", directory],
                capture_output=True, text=True,
            )

    def test_whole_file_at_policy_boundary_passes(self):
        result = self.check_entry(b"---\n" + b"a" * 15_994 + "é".encode())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("16000/16000 UTF-8 bytes", result.stdout)

    def test_one_byte_over_policy_boundary_fails(self):
        result = self.check_entry(b"---\n" + b"a" * 15_995 + "é".encode())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL mode entry", result.stdout)
        self.assertIn("16001/16000 UTF-8 bytes", result.stdout)

    def test_missing_entry_fails(self):
        result = self.check_entry(None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR mode entry", result.stderr)

    def test_invalid_utf8_fails(self):
        result = self.check_entry(b"\xff")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR mode entry", result.stderr)


if __name__ == "__main__":
    unittest.main()
