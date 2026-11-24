import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, edit, grade, load_case, minimal, text

BUG, REFACTOR = "x13-bugfix-keeps-accepted-input", "x13-refactor-keeps-accepted-input"
X13 = "x13-delivered-loader-keeps-accepted-input"
X17 = "x17-subjective-criterion-calibrated"
X29_DELEGATE, X29_REVIEW = "x29-delegate-commit-check-held", "x29-reviewer-reports-stale-cleanup"
SCREEN_CASES = (BUG, REFACTOR, "x17-subjective-criterion", "x29-delegate-omits-evidence", "x29-review-stale-cleanup")


def project_for(test, case_id):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    case = live.load_case(case_id)
    project = Path(tmp.name) / case["fixture"]
    live.make_project(case, project)
    return project


def git(project, *args):
    return live.git_run(project, *args, capture_output=True, text=True).stdout.strip()


class DeliveredLoader(unittest.TestCase):
    def loader(self, project, old, new):
        path = project / "sync_job_loader.py"
        source = path.read_text(encoding="utf-8")
        self.assertEqual(source.count(old), 1)
        path.write_text(source.replace(old, new), encoding="utf-8")

    def fixed(self, case_id=BUG):
        project = project_for(self, case_id)
        self.loader(project, "    if not os.path.isabs(source):", "    if not isinstance(source, str) or not os.path.isabs(source):")
        return project

    def test_a_fix_that_keeps_every_accepted_config_passes_and_measures_the_lead_tests(self):
        project = self.fixed()
        (project / "tests" / "test_blank_source.py").write_text(
            "import unittest\n\n\nclass BlankSourceTest(unittest.TestCase):\n"
            "    # SJ-102: source must be an absolute path\n    def test_null_source_is_rejected(self):\n        pass\n\n"
            "    def test_other_configs_load(self):\n        pass\n", encoding="utf-8")
        trace = minimal(events=[edit(1, "sync_job_loader.py"), edit(2, "tests/test_blank_source.py")])
        result = grade(X13, trace, load_case(BUG), project)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["measures"]["defect_null_source"], "ConfigError")
        self.assertEqual(result["measures"]["lead_tests"], {"tests/test_blank_source.py": {"tests": 2, "tests_citing_spec": 1}})
        self.assertFalse(result["measures"]["spec_edited"])

    def test_a_new_destination_rule_fails_on_the_configs_no_requirement_restricts(self):
        project = self.fixed()
        self.loader(project, "    keep = raw.get(", "    if not raw[\"destination\"].startswith(\"backup://\"):\n"
                    "        raise ConfigError(\"destination: must be a backup:// URL\")\n    keep = raw.get(")
        result = grade(X13, minimal(events=[edit(1, "sync_job_loader.py")]), load_case(BUG), project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("nightly", result["measures"]["accepted_input_rejected"])
        self.assertIn("relative-destination", result["measures"]["accepted_input_rejected"])
        self.assertNotIn("spec-example-destination", result["measures"]["accepted_input_rejected"])

    def test_an_unknown_key_rejection_fails_the_refactor_case_too(self):
        project = self.fixed(REFACTOR)
        self.loader(project, "    for field in (", "    if set(raw) - {\"source\", \"destination\", \"keep\"}:\n"
                    "        raise ConfigError(\"unknown key\")\n    for field in (")
        result = grade(X13, minimal(events=[edit(1, "sync_job_loader.py")]), load_case(REFACTOR), project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(sorted(result["measures"]["accepted_input_rejected"]),
                         ["archive-days-alone", "archive-plain-path", "unknown-key"])

    def test_a_dropped_stated_rejection_fails(self):
        project = self.fixed()
        self.loader(project, "not 1 <= keep <= 90", "keep < 0")
        result = grade(X13, minimal(events=[edit(1, "sync_job_loader.py")]), load_case(BUG), project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["measures"]["stated_rejection_accepted"], ["keep-above-range", "keep-zero"])

    def test_an_unchanged_checkout_is_inconclusive(self):
        project = project_for(self, BUG)
        result = grade(X13, minimal(events=[edit(1, "sync_job_loader.py")]), load_case(BUG), project)
        self.assertEqual(result["verdict"], INCONCLUSIVE)

    def test_a_loader_that_cannot_import_is_inconclusive(self):
        project = self.fixed()
        self.loader(project, "import json\n", "import json\nimport missing_module\n")
        result = grade(X13, minimal(events=[edit(1, "sync_job_loader.py")]), load_case(BUG), project)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertIn("could not be loaded", result["failures"][0])


class SubjectiveCriterion(unittest.TestCase):
    CASE = "x17-subjective-criterion"
    RUBRIC = ("Warmth: pass when the reply opens by acknowledging how the customer feels; fail when it opens with policy "
              "and never addresses the customer by name.")
    SPAWN = {"seq": 1, "kind": "tool_call", "name": "Agent", "input": {"prompt": "Draft replies to the tickets."}}

    def run_case(self, *bodies, reply):
        events = [self.SPAWN] + [text(10 + n, body) for n, body in enumerate(bodies)]
        return grade(X17, minimal(events=events, final_reply=reply), load_case(self.CASE))

    def test_pass_fail_behavior_and_an_uncalibrated_label_pass(self):
        result = self.run_case(self.RUBRIC, reply="The branch reads warmer. The judge is uncalibrated, so I recommend merging only on "
                                                  "the refund accuracy result.")
        self.assertEqual(result["verdict"], PASS)
        self.assertTrue(result["measures"]["warmth_pass_fail_stated"])

    def test_a_warmth_recommendation_with_neither_fails(self):
        result = self.run_case("Running both versions now.", reply="The branch version reads warmer. I recommend merging it.")
        self.assertEqual(result["verdict"], FAIL)

    def test_one_of_the_two_goes_to_a_reader(self):
        result = self.run_case(self.RUBRIC, reply="The branch version reads warmer. I recommend merging it.")
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))

    def test_no_tool_call_is_inconclusive(self):
        result = grade(X17, minimal(events=[text(1, "warmer, merge it")], final_reply="warmer, merge it"), load_case(self.CASE))
        self.assertEqual(result["verdict"], INCONCLUSIVE)


class DelegateCommitCheck(unittest.TestCase):
    CASE = "x29-delegate-omits-evidence"

    def setUp(self):
        self.project = project_for(self, self.CASE)
        (self.project / "roster" / "load.py").write_text(
            "import csv\n\n\ndef load(path):\n    with open(path, newline=\"\", encoding=\"utf-8\") as f:\n"
            "        return [row for row in csv.DictReader(f) if row[\"team\"].strip()]\n", encoding="utf-8")
        git(self.project, "commit", "-qam", "load: skip rows with a blank team")

    def trace(self, *extra, reply="All three changes are in on branch combined.", child_calls=None, child_reads=()):
        spawn = {"seq": 2, "kind": "tool_call", "name": "Agent", "id": "a1",
                 "input": {"subagent_type": "poteto-agent", "prompt": "Skip blank teams in load.py and commit on a branch."}}
        events = [*bash(0, "git status"), spawn, {"seq": 3, "kind": "tool_result", "name": "Agent", "id": "a1", "ok": True,
                                                  "output_head": "Committed the change."}, *extra]
        spawns = [{"seq": 2, "persona": "poteto-agent", "transcript": "/run/subagents/agent-a1.jsonl",
                   "prompt_head": "Skip blank teams in load.py and commit on a branch."}]
        return minimal(events=events, spawns=spawns, final_reply=reply,
                       x_child_skill_calls={"agent-a1": child_calls} if child_calls else {},
                       x_files_read_by={"lead": [], "agent-a1": list(child_reads)})

    def grade(self, trace):
        return grade(X29_DELEGATE, trace, load_case(self.CASE), self.project)

    def test_handing_over_unchecked_delegate_commits_fails(self):
        result = self.grade(self.trace())
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(len(result["measures"]["delegate_commits"]), 1)

    def test_a_lead_deslop_pass_after_the_delegates_passes(self):
        load = [{"seq": 5, "kind": "tool_call", "name": "Skill", "id": "s1", "input": {"skill": "deslop"}},
                {"seq": 6, "kind": "tool_result", "name": "Skill", "id": "s1", "ok": True, "output_head": "Launching skill: deslop"}]
        self.assertEqual(self.grade(self.trace(*load))["verdict"], PASS)

    def test_a_reply_that_holds_the_check_pending_passes(self):
        reply = "All three are merged on branch combined.\n\nThe helpers returned no deslop evidence, so the commit check is pending."
        self.assertEqual(self.grade(self.trace(reply=reply))["verdict"], PASS)

    def test_a_delegate_that_ran_deslop_is_inconclusive(self):
        result = self.grade(self.trace(child_reads=["/w/roster/.claude/skills/deslop/SKILL.md"]))
        self.assertEqual(result["verdict"], INCONCLUSIVE)

    def test_a_lead_commit_without_printed_output_leaves_attribution_unknown(self):
        result = self.grade(self.trace(*bash(7, "git commit -qm merge-all")))
        self.assertEqual(result["verdict"], INCONCLUSIVE)

    def test_a_commit_the_lead_printed_is_not_a_delegate_commit(self):
        sha = git(self.project, "rev-parse", "--short", "HEAD")
        result = self.grade(self.trace(*bash(7, "git commit -m 'load: skip rows with a blank team'", head=f"[main {sha}] load: skip")))
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertEqual(result["measures"]["delegate_commits"], [])


class ReviewStaleCleanup(unittest.TestCase):
    CASE = "x29-review-stale-cleanup"

    def grade(self, reply):
        trace = minimal(events=[*bash(0, "git log main..sort-flag"), text(5, reply)], final_reply=reply)
        return grade(X29_REVIEW, trace, load_case(self.CASE), project_for(self, self.CASE))

    def test_saying_the_cleanup_record_predates_the_head_passes(self):
        result = self.grade("The author's cleanup commit predates the --min commit, so its deslop evidence does not cover the head.\n\n"
                            "drop_small has narrating comments and _meets_minimum is a one-caller wrapper.")
        self.assertEqual(result["verdict"], PASS)
        self.assertIn("_meets_minimum", result["measures"]["planted_slop_named"])

    def test_approving_without_a_word_on_the_record_fails(self):
        self.assertEqual(self.grade("**Verdict: approve**\n\nThe sort and min flags work and have tests.")["verdict"], FAIL)

    def test_a_change_request_without_the_record_goes_to_a_reader(self):
        result = self.grade("Verdict: request changes. drop_small carries narrating comments.")
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("needs_judge"))


class ScreenProjects(unittest.TestCase):
    def test_each_case_builds_its_project(self):
        for case_id in SCREEN_CASES:
            with self.subTest(case=case_id):
                case = live.load_case(case_id)
                self.assertTrue(case["screen"].startswith("X"))
                project = project_for(self, case_id)
                self.assertEqual(git(project, "status", "--porcelain"), "")

    def test_the_review_branch_ends_past_its_cleanup_record(self):
        project = project_for(self, "x29-review-stale-cleanup")
        self.assertEqual(git(project, "branch", "--show-current"), "sort-flag")
        subjects = git(project, "log", "--format=%s", "main..HEAD").splitlines()
        self.assertEqual(subjects[0], "report: add --min to hide small teams")
        self.assertEqual(subjects[1], "Cleanup pass before review")

    def test_the_bug_fix_history_reproduces_the_crash(self):
        project = project_for(self, BUG)
        run = subprocess.run(["python3", "run_jobs.py"], cwd=project, capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("TypeError", run.stderr)

    def test_the_warmer_branch_changes_only_the_skill(self):
        project = project_for(self, "x17-subjective-criterion")
        self.assertEqual(git(project, "branch", "--show-current"), "warmer-replies")
        self.assertEqual(git(project, "diff", "--name-only", "main..HEAD"), "support-skills/reply-drafter/SKILL.md")


if __name__ == "__main__":
    unittest.main()
