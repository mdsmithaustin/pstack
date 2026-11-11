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

    def run_dir(self, case_id, harness, verdicts, commit="c1", grader="g1", inputs=True):
        """A graded run as live.py leaves it: the verdict, and a record whose input digests date from the run's start."""
        self.runs += 1
        run = self.out / f"run-{self.runs}"
        self.write(run / "verdict.json", json.dumps({
            "case": case_id, "harness": harness, "skills_at": commit,
            "promises": {pid: {"verdict": v} for pid, v in verdicts.items()}}))
        stored = {"inputs": {"case": freshness.case_digest(case_id, CASES[case_id], self.here), "grader": grader}} if inputs else {}
        self.write(run / "run.json", json.dumps(stored))

    def record(self, keep=False, reader_at=None):
        # By default the reader ignores the commit: the tree as it stands when the run is folded in is what it tested.
        lines = freshness.record(self.out, self.receipts, PROMISES, CASES, today="2026-11-10", here=self.here,
                                 reader_at=reader_at or (lambda commit: freshness.tree_reader(self.root)),
                                 read_now=freshness.tree_reader(self.root))
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

    def test_a_regraded_run_replaces_its_verdict_instead_of_counting_twice(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record(keep=True)
        verdict = self.out / "run-1" / "verdict.json"
        verdict.write_text(verdict.read_text().replace("PASS", "FAIL"), encoding="utf-8")
        self.record()
        entry = self.receipts["receipts"]["routes"]["claude-code"]["route-case"]
        self.assertEqual(entry["verdicts"], {"FAIL": 1})

    def test_replaying_saved_runs_cannot_clear_a_dispute(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, grader="g1")
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, grader="g2")
        self.record(keep=True)
        freshness.record_audit(self.receipts, "routes", "claude-code", "route-case", False, "keyword only", "2026-11-10")
        self.record()
        self.assertEqual(self.state("routes")[0], "disputed")

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
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, grader="g1")
        self.record()
        self.assertEqual(freshness.stale_grader(self.receipts, "g2"), 1)
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, grader="g2")
        self.record()
        entry = self.receipts["receipts"]["routes"]["claude-code"]["route-case"]
        self.assertEqual((entry["verdicts"], freshness.stale_grader(self.receipts, "g2")), ({"PASS": 1}, 0))

    def test_owner_digests_come_from_the_tested_commit_not_the_working_tree(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, commit="old")
        self.record(reader_at=lambda commit: (lambda path: f"{commit}:{path}".encode()))
        self.assertEqual(self.state("routes")[0], "stale")

    def test_an_old_run_cannot_displace_a_receipt_that_tested_the_current_tree(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        self.run_dir("route-case", "claude-code", {"routes": "FAIL"}, commit="old")
        lines = self.record(reader_at=lambda commit: (lambda path: f"{commit}:{path}".encode()))
        self.assertEqual(self.state("routes"), ("fresh", "PASS 1"))
        self.assertIn("this run did not", lines[0])

    def test_a_run_keeps_the_case_digest_it_started_with(self):
        # Folding an old output directory in after its fixture changed must not credit the old verdict with the new bytes.
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record(keep=True)
        self.write(self.here / "fixtures" / "tally" / "tally.py", "print(2)\n")
        self.record()
        self.assertEqual(self.state("routes")[0], "stale")

    def test_a_run_whose_record_has_no_input_digests_leaves_no_receipt(self):
        self.run_dir("route-case", "claude-code", {"routes": "PASS"}, inputs=False)
        lines = self.record()
        self.assertEqual(self.receipts["receipts"], {})
        self.assertIn("carries no input digests", lines[0])

    def test_an_inconclusive_verdict_is_debt_until_a_reader_or_a_rerun_decides(self):
        self.run_dir("route-case", "claude-code", {"routes": "INCONCLUSIVE"})
        self.record()
        self.assertEqual(self.state("routes"), ("unresolved", "graded INCONCLUSIVE in 1 run(s); a reader or a rerun must decide"))
        freshness.record_audit(self.receipts, "routes", "claude-code", "route-case", True, "the run could not show it", "2026-11-10")
        self.assertEqual(self.state("routes"), ("fresh", "INCONCLUSIVE 1"))


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

    def test_a_multi_turn_case_costs_its_limit_for_every_turn(self):
        CASES["route-case"]["turns"] = ["a", "b", "c", "d"]
        self.addCleanup(CASES["route-case"].pop, "turns")
        plan = freshness.plan(self.rows(), CASES, budget_s=1000)["claude-code"]
        self.assertEqual((plan["cases"], plan["uncovered"]), ([], ["builds", "routes"]))
        self.assertEqual(freshness.plan(self.rows(), CASES)["claude-code"]["timeout_s_upper_bound"], 1800)

    def test_an_arm_case_is_never_planned_because_its_verdict_is_never_recorded(self):
        CASES["arm-case"] = {"promises": ["routes"], "fixture": "tally", "timeout_s": 1, "skill_overlays": [{"file": "a/SKILL.md"}]}
        self.addCleanup(CASES.pop, "arm-case")
        plan = freshness.plan(self.rows(), CASES)["claude-code"]
        self.assertNotIn("arm-case", [pick["case"] for pick in plan["cases"]])

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

    def test_a_deleted_fixture_still_reaches_the_cases_that_used_it(self):
        shutil.rmtree(self.here / "fixtures" / "tally")
        reached = {row["promise"] for row in freshness.touched(
            self.rows(), ["evals/promises/fixtures/tally/tally.py"], CASES, here=self.here, root=self.root)}
        self.assertEqual(reached, {"routes", "builds"})

    def test_a_case_that_borrows_another_cases_checks_goes_stale_with_them(self):
        CASES["build-case"]["references"] = "route-case"
        self.addCleanup(CASES["build-case"].pop, "references")
        self.run_dir("build-case", "claude-code", {"builds": "PASS"})
        self.record()
        self.assertEqual(self.state("builds")[0], "fresh")
        self.write(self.here / "cases" / "route-case" / "held_out.py", "assert True\n")
        self.assertEqual(self.state("builds"), ("stale", "case, fixture, or history changed"))


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
        self.run_dir("build-case", "claude-code", {"routes": "FAIL"}, grader="g2")
        self.record()
        self.assertEqual(self.state("routes")[0], "unsettled")

    def test_the_sample_reaches_an_unread_pass_on_a_case_that_does_not_represent_its_cell(self):
        freshness.record_audit(self.receipts, "routes", "claude-code", "build-case", True, None, "2026-11-10")
        self.run_dir("route-case", "claude-code", {"routes": "PASS"})
        self.record()
        sample = freshness.audit_sample(self.receipts, self.rows(), 5)
        self.assertEqual([(s["promise"], s["case"]) for s in sample], [("routes", "route-case")])

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

    def test_a_live_run_record_carries_the_digests_record_reads(self):
        import case_inputs
        import live
        case = live.load_case("route-feature")
        run = live.Run(Path("/nonexistent"), "codex", case, "c1", 300, inputs=case_inputs.run_inputs(case))
        spec = freshness.load_cases()["route-feature"]
        self.assertEqual(live.meta(run)["inputs"], {"case": freshness.case_digest("route-feature", spec),
                                                    "grader": freshness.grader_digest()})

    def test_strict_check_passes_on_the_committed_tree(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = freshness.main(["check", "--strict"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("live promise cells: "))


if __name__ == "__main__":
    unittest.main()
