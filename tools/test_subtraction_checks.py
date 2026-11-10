import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOVAL = ROOT / "tools/check-removal.py"
BYTES = ROOT / "tools/check-route-bytes.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


removal = load(REMOVAL, "check_removal")


class Mentions(unittest.TestCase):
    def test_code_bold_slash_and_path_forms_count(self):
        for text in ("Call the Skill tool with `how`.", "the **how** skill", "run /how first", "see ../how/SKILL.md", '"how",'):
            with self.subTest(text=text):
                self.assertTrue(removal.mentions("how", text))

    def test_plain_words_and_longer_names_do_not_count(self):
        for text in ("how does this work", "`how-to`", "/however", "showhow/"):
            with self.subTest(text=text):
                self.assertFalse(removal.mentions("how", text))


class RemovalRatchet(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ("alpha", "beta"):
            (self.root / "skills" / name).mkdir(parents=True)
            (self.root / "skills" / name / "SKILL.md").write_text(f"# {name}\n")
        (self.root / "agents").mkdir()
        self.baseline = self.root / "baseline.json"

    def run_check(self, *args):
        return subprocess.run([sys.executable, str(REMOVAL), "--root", str(self.root), "--baseline", str(self.baseline), *args],
                              capture_output=True, text=True)

    def test_a_new_mention_fails_until_reviewed(self):
        self.assertEqual(self.run_check("--update").returncode, 0)
        self.assertEqual(self.run_check().returncode, 0)
        (self.root / "skills/beta/SKILL.md").write_text("Call the Skill tool with `alpha`.\n")
        done = self.run_check()
        self.assertEqual(done.returncode, 1)
        self.assertIn("alpha is named in 1 shipped files, above its baseline of 0", done.stdout)
        self.assertEqual(self.run_check("--update").returncode, 1)
        self.assertEqual(self.run_check("--update", "--allow-raise").returncode, 0)

    def test_a_removed_mention_passes_and_can_tighten(self):
        (self.root / "skills/beta/SKILL.md").write_text("the **alpha** skill\n")
        self.run_check("--update")
        (self.root / "skills/beta/SKILL.md").write_text("# beta\n")
        done = self.run_check()
        self.assertEqual(done.returncode, 0)
        self.assertIn("1 below it", done.stdout)
        self.run_check("--update")
        self.assertEqual(json.loads(self.baseline.read_text())["alpha"], 0)

    def test_a_skill_without_a_baseline_entry_fails(self):
        self.baseline.write_text("{}\n")
        self.assertIn("has no baseline entry", self.run_check().stdout)

    def test_report_lists_the_files(self):
        (self.root / "agents/x.md").write_text("load `alpha`\n")
        self.assertIn("  agents/x.md", self.run_check("--report", "alpha").stdout)

    def test_the_committed_baseline_holds(self):
        done = subprocess.run([sys.executable, str(REMOVAL)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)


class RouteBytes(unittest.TestCase):
    def test_the_committed_budgets_hold(self):
        done = subprocess.run([sys.executable, str(BYTES)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_lighter_route_never_loads_more_than_a_heavier_one(self):
        report = load(BYTES, "check_route_bytes").measure(ROOT)
        for playbook in ("bug-fix", "feature", "refactoring", "perf-issue"):
            sizes = [report[f"{playbook}:{route}"]["bytes"] for route in ("lightweight", "standard", "intensive")]
            self.assertEqual(sizes, sorted(sizes), playbook)

    def test_a_budget_below_the_load_fails_and_update_will_not_raise_it(self):
        with tempfile.TemporaryDirectory() as directory:
            budgets = Path(directory) / "budgets.json"
            subprocess.run([sys.executable, str(BYTES), "--budgets", str(budgets), "--update"], check=True, capture_output=True)
            data = json.loads(budgets.read_text())
            data["investigation"] -= 1
            budgets.write_text(json.dumps(data))
            done = subprocess.run([sys.executable, str(BYTES), "--budgets", str(budgets)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertIn("investigation loads", done.stdout)
            again = subprocess.run([sys.executable, str(BYTES), "--budgets", str(budgets), "--update"], capture_output=True, text=True)
            self.assertEqual(again.returncode, 1)


if __name__ == "__main__":
    unittest.main()
