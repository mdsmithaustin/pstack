import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import freshness
import ledger

PROMISES = {
    "routes": {"check": "live", "owners": ["skills/a/SKILL.md"]},
    "builds": {"check": "live", "owners": ["skills/a/SKILL.md", "skills/b/SKILL.md"]},
    "parked": {"check": "live", "owners": ["skills/b/SKILL.md"]},
    "quoted": {"check": "static", "owners": ["skills/a/SKILL.md"]},
}
CASES = {
    "route-case": {"promises": ["routes"], "fixture": "tally", "timeout_s": 300},
    "build-case": {"promises": ["routes", "builds"], "fixture": "tally", "timeout_s": {"default": 1800, "codex": 2400}},
    "parked-case": {"promises": ["parked"], "fixture": "tally", "deferred": "needs a remote"},
}


class Tree(unittest.TestCase):
    """A small promise tree on disk, with skill files a test can edit to stale a receipt."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-freshness-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.here = self.root / "evals" / "promises"
        self.out = self.root / "out"
        for case_id, spec in CASES.items():
            self.write(self.here / "cases" / case_id / "case.json", json.dumps(spec))
        self.write(self.here / "fixtures" / "tally" / "tally.py", "print(1)\n")
        self.write(self.root / "skills/a/SKILL.md", "route here\n")
        self.write(self.root / "skills/b/SKILL.md", "build here\n")
        self.receipts = {"version": 1, "receipts": {}}
        self.runs = 0

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_dir(self, case_id, harness, verdicts, commit="c1"):
        self.runs += 1
        self.write(self.out / f"run-{self.runs}" / "verdict.json", json.dumps({
            "case": case_id, "harness": harness, "skills_at": commit,
            "promises": {pid: {"verdict": v} for pid, v in verdicts.items()}}))

    def record(self, grader="g1", keep=False):
        # The reader ignores the commit: these tests record the tree as it stands when the run is folded in.
        lines = freshness.record(self.out, self.receipts, PROMISES, CASES, today="2026-11-10", grader=grader, here=self.here,
                                 reader_at=lambda commit: freshness.tree_reader(self.root), read_now=freshness.tree_reader(self.root))
        if not keep:
            shutil.rmtree(self.out)
        return lines

    def rows(self, harnesses=("claude-code",)):
        return freshness.cells(self.receipts, PROMISES, CASES, harnesses, read=freshness.tree_reader(self.root),
                               applies=lambda pid, harness: True, here=self.here)

    def state(self, pid, harness="claude-code"):
        return next((row["state"], row["reason"]) for row in self.rows((harness,)) if row["promise"] == pid)


class Cells(Tree):
    def test_a_live_promise_with_no_receipt_is_missing_and_a_static_one_is_not_listed(self):
        rows = self.rows()
        self.assertEqual({row["promise"]: row["state"] for row in rows},
                         {"routes": "missing", "builds": "missing", "parked": "deferred"})

    def test_a_recorded_verdict_is_fresh_until_an_owner_changes(self):
        self.run_dir("build-case", "claude-code", {"routes": "PASS", "builds": "FAIL"})
        self.record()
        self.assertEqual(self.state("builds"), ("fresh", "FAIL 1"))
        self.write(self.root / "skills/b/SKILL.md", "build differently\n")
        self.assertEqual(self.state("builds"), ("stale", "owner changed: skills/b/SKILL.md"))
        self.assertEqual(self.state("routes")[0], "fresh")

    def test_a_changed_fixture_stales_every_receipt_from_cases_that_use_it(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.write(self.here / "fixtures" / "tally" / "tally.py", "print(2)\n")
        self.assertEqual(self.state("routes"), ("stale", "case, fixture, or history changed"))

    def test_a_receipt_on_one_harness_is_not_evidence_for_another(self):
        self.run_dir("route-case", "codex", {"routes": "PASS"})
        self.record()
        self.assertEqual(self.state("routes", "codex")[0], "fresh")
        self.assertEqual(self.state("routes", "claude-code")[0], "missing")

    def test_one_fresh_bound_case_covers_a_promise_two_cases_grade(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.assertEqual(self.state("routes")[0], "fresh")

    def test_a_harness_the_promise_does_not_apply_to_gets_no_row(self):
        rows = freshness.cells(self.receipts, PROMISES, CASES, ("claude-code", "codex"), read=freshness.tree_reader(self.root),
                               applies=lambda pid, harness: harness == "codex", here=self.here)
        self.assertEqual({row["harness"] for row in rows}, {"codex"})


class Record(Tree):
    def test_a_login_death_and_an_arm_case_leave_no_receipt(self):
        self.run_dir("route-case", "claude-code", {"routes": "ERROR"})
        CASES["arm-case"] = {"promises": ["routes"], "fixture": "tally", "skill_overlays": [{"file": "a/SKILL.md"}]}
        self.addCleanup(CASES.pop, "arm-case")
        self.run_dir("arm-case", "claude-code", {"routes": "PASS"})
        lines = self.record()
        self.assertEqual(self.receipts["receipts"], {})
        self.assertTrue(any("arm case" in line for line in lines))

    def test_a_verdict_that_matches_the_one_it_replaces_settles_in_one_run(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.write(self.root / "skills/a/SKILL.md", "route here, reworded\n")
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.assertEqual(self.state("routes"), ("fresh", "PASS 1"))

    def test_a_flipped_verdict_stays_unsettled_until_three_runs_on_the_same_bytes(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.write(self.root / "skills/a/SKILL.md", "route elsewhere\n")
        self.run_dir("route-case", "claude-code", {"routes": "FAIL"})
        self.record()
        self.assertEqual(self.state("routes"), ("unsettled", "changed from PASS to FAIL after 1 run(s); needs 3"))
        for _ in range(2):
            self.run_dir("route-case", "claude-code", {"routes": "FAIL"})
        self.record()
        self.assertEqual(self.state("routes"), ("fresh", "FAIL 3"))

    def test_folding_the_same_output_in_twice_counts_each_run_once(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record(keep=True)
        self.record()
        self.assertEqual(self.state("routes"), ("fresh", "PASS 1"))

    def test_runs_that_disagree_are_unsettled_and_then_reported_as_mixed(self):
        for verdict in ("PASS", "FAIL"):
            self.run_dir("route-case", "claude-code", {"routes": verdict})
        self.record()
        self.assertEqual(self.state("routes")[0], "unsettled")
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.assertEqual(self.state("routes"), ("fresh", "FAIL 1, PASS 2"))

    def test_a_grader_change_restarts_the_count_and_is_reported_for_regrading(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record(grader="g1")
        self.assertEqual(freshness.stale_grader(self.receipts, "g2"), 1)
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record(grader="g2")
        entry = self.receipts["receipts"]["routes"]["claude-code"]["route-case"]
        self.assertEqual((entry["verdicts"], freshness.stale_grader(self.receipts, "g2")), ({"PASS": 1}, 0))

    def test_owner_digests_come_from_the_tested_commit_not_the_working_tree(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, commit="old")
        at_commit = lambda commit: (lambda path: f"{commit}:{path}".encode())
        freshness.record(self.out, self.receipts, PROMISES, CASES, today="2026-11-10", grader="g", here=self.here,
                         reader_at=at_commit, read_now=freshness.tree_reader(self.root))
        self.assertEqual(self.state("routes")[0], "stale")

    def test_an_old_run_cannot_displace_a_receipt_that_tested_the_current_tree(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.run_dir("route-case", "claude-code", {"routes": "FAIL"}, commit="old")
        lines = freshness.record(self.out, self.receipts, PROMISES, CASES, today="2026-11-10", grader="g1", here=self.here,
                                 reader_at=lambda commit: (lambda path: f"{commit}:{path}".encode()),
                                 read_now=freshness.tree_reader(self.root))
        self.assertEqual(self.state("routes"), ("fresh", "PASS 1"))
        self.assertIn("this run did not", lines[0])


class Plan(Tree):
    def test_the_plan_picks_the_case_that_settles_the_most_per_second(self):
        plan = freshness.plan(self.rows(), CASES)["claude-code"]
        self.assertEqual([pick["case"] for pick in plan["cases"]], ["route-case", "build-case"])
        self.assertEqual((plan["timeout_s_upper_bound"], plan["uncovered"]), (2100, []))
        self.assertEqual(plan["command"], "python3 evals/promises/live.py run --harness claude-code --case route-case --case build-case")

    def test_a_budget_leaves_what_it_cannot_afford_listed_as_uncovered(self):
        plan = freshness.plan(self.rows(), CASES, budget_s=600)["claude-code"]
        self.assertEqual(([pick["case"] for pick in plan["cases"]], plan["uncovered"]), (["route-case"], ["builds"]))

    def test_the_time_limit_is_read_for_the_planned_harness(self):
        plan = freshness.plan(self.rows(("codex",)), CASES)["codex"]
        self.assertEqual(plan["timeout_s_upper_bound"], 2700)

    def test_an_unsettled_cell_is_planned_on_the_case_its_receipt_came_from(self):
        for verdict in ("PASS", "FAIL"):
            self.run_dir("build-case", "claude-code", {"routes": verdict, "builds": "PASS"})
        self.record()
        plan = freshness.plan([row for row in self.rows() if row["promise"] == "routes"], CASES)["claude-code"]
        self.assertEqual(([pick["case"] for pick in plan["cases"]], plan["repeat_until_settled"]), (["build-case"], ["build-case"]))

    def test_fresh_and_deferred_cells_need_no_run(self):
        self.run_dir("build-case", "claude-code", {"routes": "PASS", "builds": "PASS"})
        self.record()
        plan = freshness.plan(self.rows(), CASES)["claude-code"]
        self.assertEqual((plan["cases"], plan["command"]), ([], None))


class Touched(Tree):
    def test_a_change_reaches_promises_by_owner_and_by_case_input(self):
        rows = self.rows()
        def reached(*changed):
            return {row["promise"] for row in freshness.touched(rows, changed, CASES, here=self.here, root=self.root)}
        self.assertEqual(reached("skills/b/SKILL.md"), {"builds", "parked"})
        self.assertEqual(reached("evals/promises/cases/route-case/case.json"), {"routes"})
        self.assertEqual(reached("evals/promises/fixtures/tally/tally.py"), {"routes", "builds"})
        self.assertEqual(reached("README.md", "skills/a/references/x.md"), set())


class Audit(Tree):
    def setUp(self):
        super().setUp()
        self.run_dir("build-case", "claude-code", {"routes": "PASS", "builds": "FAIL"})
        self.record()

    def test_the_sample_names_only_unread_fresh_passes(self):
        sample = freshness.audit_sample(self.receipts, self.rows(), 5)
        self.assertEqual([(s["promise"], s["case"]) for s in sample], [("routes", "build-case")])
        freshness.record_audit(self.receipts, "routes", "claude-code", "build-case", True, None, "2026-11-10")
        self.assertEqual(freshness.audit_sample(self.receipts, self.rows(), 5), [])

    def test_a_disputed_pass_is_debt_until_it_is_rerun(self):
        freshness.record_audit(self.receipts, "routes", "claude-code", "build-case", False, "keyword only", "2026-11-10")
        self.assertEqual(self.state("routes"), ("disputed", "a reader disagreed with the recorded verdict"))
        self.run_dir("build-case", "claude-code", {"routes": "FAIL"})
        self.record(grader="g2")
        self.assertEqual(self.state("routes")[0], "unsettled")

    def test_an_audit_of_a_receipt_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            freshness.record_audit(self.receipts, "routes", "codex", "build-case", True, None, "2026-11-10")


class Check(Tree):
    def test_only_a_blocking_promise_in_debt_is_marked(self):
        lines = freshness.render_check(self.rows(), {"routes"}, 2)
        self.assertEqual(lines[0], "live promise cells: 3; missing 2; deferred 1")
        self.assertIn("missing   claude-code routes [blocking]: no receipt", lines)
        self.assertIn("missing   claude-code builds: no receipt", lines)
        self.assertIn("2 receipt(s) were graded by an earlier grader", lines[-1])
        quiet = freshness.render_check(self.rows(), {"routes"}, 0, quiet=True)
        self.assertEqual(quiet[1:], ["missing   claude-code routes [blocking]: no receipt"])


class Committed(unittest.TestCase):
    def test_the_committed_receipts_are_canonical_and_name_ledger_promises_and_cases(self):
        text = freshness.RECEIPTS.read_text(encoding="utf-8")
        book = ledger.parse(text)
        self.assertEqual(text, ledger.canonical(book))
        promises, cases = ledger.load()["promises"], freshness.load_cases()
        for pid, by_harness in book["receipts"].items():
            self.assertIn(pid, promises)
            for harness, by_case in by_harness.items():
                self.assertIn(harness, freshness.report.HARNESSES)
                self.assertLessEqual(set(by_case), set(cases))

    def test_the_policy_names_known_harnesses_and_live_promises(self):
        policy = freshness.load_policy()
        promises = ledger.load()["promises"]
        self.assertTrue(policy["harnesses"])
        for pid in policy["blocking"]:
            self.assertEqual(promises[pid]["check"], "live", pid)

    def test_strict_check_passes_on_the_committed_tree(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = freshness.main(["check", "--strict"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("live promise cells: "))


if __name__ == "__main__":
    unittest.main()
