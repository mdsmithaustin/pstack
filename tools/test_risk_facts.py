import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/poteto-mode/scripts/risk-facts.py"


class RiskFacts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "Test")
        (self.repo / "tests").mkdir()
        self.write("pricing.py", "def total(items):\n    return sum(items)\n", "add pricing")
        self.write("cart.py", "from pricing import total\n", "add cart")
        self.write("tests/test_pricing.py", "from pricing import total\n", "test pricing")
        self.write("pricing.py", "def total(items):\n    return sum(items or [])\n", "fix empty cart regression")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def write(self, name, text, message):
        (self.repo / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-q", "-m", message)

    def facts(self, *args, env=None):
        done = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.repo), "--json", *args],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_history_counts_commits_and_repairs(self):
        past = self.facts("pricing.py")["paths"][0]["history"]
        self.assertEqual((past["commits"], past["repair_commits"], past["tracked"]), (2, 1, True))

    def test_text_reach_separates_callers_from_tests_and_names_its_source(self):
        reach = self.facts("pricing.py", "--symbol", "total")["symbols"][0]
        self.assertEqual(reach["source"], "git grep (symbol)")
        self.assertEqual(reach["files"], ["cart.py", "pricing.py"])
        self.assertEqual(reach["tests"], ["tests/test_pricing.py"])

    def test_a_caller_with_a_non_ascii_name_keeps_its_real_path(self):
        self.write("café.py", "from pricing import total\n", "add café")
        reach = self.facts("pricing.py", "--symbol", "total")["symbols"][0]
        self.assertIn("café.py", reach["files"])

    def test_untracked_path_is_flagged(self):
        (self.repo / "new.py").write_text("x = 1\n")
        entry = self.facts("new.py")["paths"][0]
        self.assertFalse(entry["history"]["tracked"])
        self.assertIn("absent from any GitNexus index", entry["note"])

    def test_without_gitnexus_the_fallback_is_stated(self):
        notes = self.facts("pricing.py")["notes"]
        self.assertTrue(any("git grep" in note for note in notes))

    def fake_gitnexus(self, body):
        (self.repo / ".gitnexus").mkdir()
        bin_dir = Path(self.directory.name) / "bin"
        bin_dir.mkdir()
        tool = bin_dir / "gitnexus"
        tool.write_text("#!/bin/sh\n" + body)
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def test_gitnexus_supplies_symbol_reach_when_indexed(self):
        env = self.fake_gitnexus('if [ "$1" = impact ]; then echo "cart.py:1 calls $2"; fi\n')
        reach = self.facts("pricing.py", "--symbol", "total", env=env)["symbols"][0]
        self.assertEqual(reach["source"], "gitnexus impact")
        self.assertEqual(reach["output"], ["cart.py:1 calls total"])

    def test_failing_gitnexus_falls_back_and_says_so(self):
        env = self.fake_gitnexus('if [ "$1" = impact ]; then exit 3; fi\n')
        report = self.facts("pricing.py", "--symbol", "total", env=env)
        self.assertEqual(report["symbols"][0]["source"], "git grep (symbol)")
        self.assertTrue(any("gitnexus impact total failed" in note for note in report["notes"]))

    def test_a_failed_search_is_unavailable_not_zero(self):
        bin_dir = Path(self.directory.name) / "gitbin"
        bin_dir.mkdir()
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True).stdout.strip()
        tool = bin_dir / "git"
        tool.write_text(f'#!/bin/sh\nfor a in "$@"; do if [ "$a" = grep ]; then echo boom >&2; exit 128; fi; done\nexec {real} "$@"\n')
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        report = self.facts("pricing.py", "--symbol", "total", env=env)
        self.assertTrue(report["symbols"][0]["unavailable"])
        self.assertIsNone(report["symbols"][0]["other_files"])
        self.assertTrue(report["paths"][0]["reach"]["unavailable"])
        text = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.repo), "pricing.py"],
                              capture_output=True, text=True, env=env).stdout
        self.assertIn("unavailable, the search failed. Pass --symbol, or record reach as unknown.", text)

    def test_a_missing_path_is_an_error_not_a_zero(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.repo), "pricng.py"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("does not exist", done.stderr)

    def test_a_generic_file_name_gives_no_reassuring_zero(self):
        (self.repo / "index.py").write_text("x = 1\n")
        reach = self.facts("index.py")["paths"][0]["reach"]
        self.assertTrue(reach["unavailable"])
        self.assertIsNone(reach["other_files"])

    def test_a_silent_or_hanging_gitnexus_falls_back(self):
        env = self.fake_gitnexus('if [ "$1" = impact ]; then exit 0; fi\n')
        report = self.facts("pricing.py", "--symbol", "total", env=env)
        self.assertEqual(report["symbols"][0]["source"], "git grep (symbol)")

    def test_whole_word_matching_ignores_longer_names(self):
        self.write("subtotal.py", "def subtotal_total_x():\n    return 1\n", "add subtotal")
        reach = self.facts("pricing.py", "--symbol", "total")["symbols"][0]
        self.assertNotIn("subtotal.py", reach["files"])

    def test_running_from_a_subdirectory_still_names_repository_paths(self):
        (self.repo / "pkg").mkdir()
        self.write("pkg/tax.py", "from pricing import total\n", "add tax")
        done = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.repo / "pkg"), "--json", "tax.py", "--symbol", "total"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        reach = json.loads(done.stdout)["symbols"][0]
        self.assertIn("cart.py", reach["files"])
        self.assertIn("tests/test_pricing.py", reach["tests"])

    def test_a_failed_history_query_is_unavailable_not_zero(self):
        bin_dir = Path(self.directory.name) / "logbin"
        bin_dir.mkdir()
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True).stdout.strip()
        tool = bin_dir / "git"
        tool.write_text(f'#!/bin/sh\nfor a in "$@"; do if [ "$a" = log ]; then echo boom >&2; exit 128; fi; done\nexec {real} "$@"\n')
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        past = self.facts("pricing.py", env=env)["paths"][0]["history"]
        self.assertTrue(past["unavailable"])
        self.assertIsNone(past["commits"])
        text = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.repo), "pricing.py"],
                              capture_output=True, text=True, env=env).stdout
        self.assertIn("history (git log): unavailable", text)

    def test_no_match_is_a_real_zero(self):
        reach = self.facts("pricing.py", "--symbol", "nothing_names_this")["symbols"][0]
        self.assertEqual((reach.get("unavailable"), reach["other_files"]), (None, 0))

    def test_outside_a_repository_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            done = subprocess.run([sys.executable, str(SCRIPT), "--project", directory, "a.py"], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
