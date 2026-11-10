import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNUSED = ROOT / "tools/unused-skills.py"
BYTES = ROOT / "tools/check-route-bytes.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unused = load(UNUSED, "unused_skills")


class Mentions(unittest.TestCase):
    def test_code_bold_slash_and_path_forms_count(self):
        for text in ("Call the Skill tool with `how`.", "the **how** skill", "run /how first", "see ../how/SKILL.md", '"how",'):
            with self.subTest(text=text):
                self.assertTrue(unused.mentions("how", text))

    def test_plain_words_and_longer_names_do_not_count(self):
        for text in ("how does this work", "`how-to`", "/however", "showhow/"):
            with self.subTest(text=text):
                self.assertFalse(unused.mentions("how", text))


class UnusedSkills(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ("alpha", "beta", "gamma"):
            (self.root / "skills" / name).mkdir(parents=True)
            (self.root / "skills" / name / "SKILL.md").write_text(f"# {name}\n")
        (self.root / "agents").mkdir()
        (self.root / "evals/promises").mkdir(parents=True)
        (self.root / "evals/promises/ledger.json").write_text(json.dumps(
            {"promises": {"p": {"owners": ["skills/gamma/SKILL.md"]}}}))
        (self.root / "skills/beta/SKILL.md").write_text("Call the Skill tool with `alpha`.\n")

    def rows(self):
        return unused.report(self.root)

    def test_a_skill_another_skill_loads_is_in_use(self):
        row = self.rows()["alpha"]
        self.assertEqual((row["loaded_by"], row["candidate"], row["index_only"]), (1, False, False))

    def test_a_skill_nothing_loads_or_promises_is_a_candidate(self):
        self.assertTrue(self.rows()["beta"]["candidate"])

    def test_a_promised_skill_nothing_loads_is_index_only(self):
        row = self.rows()["gamma"]
        self.assertEqual((row["candidate"], row["index_only"], row["promises"]), (False, True, 1))

    def test_a_corpus_keeps_a_skill_off_the_candidate_list(self):
        (self.root / "evals/beta").mkdir()
        self.assertFalse(self.rows()["beta"]["candidate"])

    def test_the_report_never_fails_the_build(self):
        done = subprocess.run([sys.executable, str(UNUSED), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertIn("beta: candidate", done.stdout)
        self.assertIn("gamma: index only", done.stdout)
        self.assertIn("This report gates nothing.", done.stdout)


class RouteBytes(unittest.TestCase):
    def test_the_committed_budgets_hold(self):
        done = subprocess.run([sys.executable, str(BYTES)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_lighter_route_never_loads_more_than_a_heavier_one(self):
        report = load(BYTES, "check_route_bytes").measure(ROOT)
        for playbook in ("bug-fix", "feature", "refactoring", "perf-issue"):
            sizes = [report[f"{playbook}:{route}"]["markdown"] for route in ("lightweight", "standard", "intensive")]
            self.assertEqual(sizes, sorted(sizes), playbook)

    def test_context_counts_plan_output_and_linked_reads_but_no_script_source(self):
        report = load(BYTES, "check_route_bytes").measure(ROOT)
        review = report["code-review"]
        self.assertGreater(review["plan_output"], 0)
        self.assertEqual(review["bytes"], review["markdown"] + review["plan_output"])
        self.assertIn("skills/interrogate/references/code-quality-review.md", review["files"])
        self.assertIn("skills/poteto-mode/references/review-lens.md", review["files"])
        self.assertIn("skills/poteto-mode/playbooks/opening-a-pr.md", report["shipping"]["files"])
        for value in report.values():
            self.assertTrue(all(name.endswith(".md") for name in value["files"]), value["files"])

    def test_conditional_and_non_read_mentions_are_not_counted(self):
        report = load(BYTES, "check_route_bytes").measure(ROOT)
        self.assertNotIn("skills/poteto-mode/playbooks/opening-a-pr.md", report["code-review"]["files"])
        self.assertNotIn("skills/pstack-harness/references/loops.md", report["bug-fix:standard"]["files"])
        self.assertNotIn("skills/poteto-mode/references/delegation.md", report["feature:lightweight"]["files"])
        self.assertIn("skills/poteto-mode/references/delegation.md", report["feature:standard"]["files"])

    def test_the_gated_reference_is_not_counted_on_any_route(self):
        report = load(BYTES, "check_route_bytes").measure(ROOT)
        for key, value in report.items():
            self.assertNotIn("skills/poteto-mode/references/gated-publish.md", value["files"], key)

    def test_surface_reports_scripts_apart_from_context(self):
        done = subprocess.run([sys.executable, str(BYTES), "--surface"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertIn("skill scripts", done.stdout)
        self.assertIn("None of it is placed in the lead's context", done.stdout)

    def test_the_measure_does_not_depend_on_the_checkout_path_or_installed_tools(self):
        module = load(BYTES, "check_route_bytes")
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "a-much-longer-checkout-directory-name" / "repo"
            copy.parent.mkdir()
            shutil.copytree(ROOT / "skills", copy / "skills", ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
            (copy / "tools").mkdir()
            shutil.copy(BYTES, copy / "tools/check-route-bytes.py")
            done = subprocess.run([sys.executable, str(copy / "tools/check-route-bytes.py"), "--budgets",
                                   str(ROOT / "tools/route-byte-budgets.json")], capture_output=True, text=True,
                                  env={"PATH": "/usr/bin:/bin"}, cwd=directory)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

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
