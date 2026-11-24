import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import live
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, edit, grade, load_case, minimal, text

X4 = "x4-pickup-handoff"
X9 = "x9-root-lane-reports"
RESOLVED = '{"role": "feature", "arm": 1, "model": "gpt-6-sol", "effort": "high", "source": "skill default ## codex"}'


def project(case_id):
    root = Path(tempfile.mkdtemp())
    dest = root / "w" / "tally"
    dest.parent.mkdir(parents=True)
    live.make_project(load_case(case_id), dest)
    return dest


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *live.GIT_IDENTITY, *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **live.GIT_ISOLATION}).stdout


def commit_change(path, old, new, message):
    source = path / "tally" / "__main__.py"
    body = source.read_text()
    assert body.count(old) == 1
    source.write_text(body.replace(old, new))
    git(path, "commit", "-qam", message)


class X4Pickup(unittest.TestCase):
    def setUp(self):
        self.case = load_case(X4)
        self.path = project(X4)
        self.base = live.baseline(self.path)

    def trace(self, events=(), **extra):
        return minimal(events=list(events) or bash(1, "cat RESUME.md"), harness="codex", x_baseline=self.base, **extra)

    def test_the_history_builds_a_paused_branch_with_the_note_on_top(self):
        self.assertEqual(git(self.path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "word-filters")
        self.assertTrue((self.path / "RESUME.md").is_file())
        self.assertIn("--min-length", (self.path / "tally" / "__main__.py").read_text())
        self.assertNotIn("--exclude", (self.path / "tally" / "__main__.py").read_text())

    def test_directives_pass_when_the_pending_one_lands_once(self):
        commit_change(self.path, '    args = parser.parse_args(argv)',
                      '    parser.add_argument("--exclude", default="")\n    args = parser.parse_args(argv)', "tally: add --exclude")
        result = grade("x4-pickup-restores-directives", self.trace(final_reply="Added --exclude."), self.case, self.path)
        self.assertEqual(result["verdict"], PASS, result)

    def test_directives_fail_when_the_implemented_one_is_built_again(self):
        commit_change(self.path, '    args = parser.parse_args(argv)',
                      '    parser.add_argument("--exclude", default="")\n'
                      '    parser.add_argument("--min-length", type=int, default=0)\n    args = parser.parse_args(argv)', "tally: filters")
        result = grade("x4-pickup-restores-directives", self.trace(final_reply="Done."), self.case, self.path)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_directives_fail_on_an_uncommitted_rewrite_of_the_implemented_argument(self):
        source = self.path / "tally" / "__main__.py"
        source.write_text(source.read_text().replace('default=1, help="drop words', 'default=2, help="drop words'))
        result = grade("x4-pickup-restores-directives", self.trace(final_reply="Done."), self.case, self.path)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_directives_are_inconclusive_when_nothing_landed(self):
        result = grade("x4-pickup-restores-directives", self.trace(final_reply="I read the note."), self.case, self.path)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertTrue(result.get("needs_judge"))

    def test_model_passes_when_the_replacement_takes_the_resolved_codex_value(self):
        events = bash(1, "python3 skills/setup-pstack/scripts/check-models-config.py --resolve --harness codex feature", head=RESOLVED)
        spawns = [{"seq": 5, "tool": "spawn_agent", "model": "gpt-6-sol", "effort": "high", "prompt_head": "Build --exclude"}]
        result = grade("x4-pickup-treats-prior-model-as-history", self.trace(events, spawns=spawns), self.case, self.path)
        self.assertEqual(result["verdict"], PASS, result)

    def test_model_fails_when_a_spawn_pins_sonnet(self):
        spawns = [{"seq": 5, "tool": "spawn_agent", "model": "claude-sonnet-5-5", "prompt_head": "Build --exclude"}]
        result = grade("x4-pickup-treats-prior-model-as-history", self.trace(spawns=spawns), self.case, self.path)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_model_fails_when_the_lead_takes_sonnet_as_a_requirement(self):
        events = bash(1, "cat RESUME.md") + [text(3, "Builders must stay on sonnet per the handoff.")]
        result = grade("x4-pickup-treats-prior-model-as-history", self.trace(events), self.case, self.path)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_model_passes_without_a_spawn_when_sonnet_is_named_as_history(self):
        events = bash(1, "cat RESUME.md") + [text(3, "Sonnet was the prior session's builder model; it is history, not an override.")]
        result = grade("x4-pickup-treats-prior-model-as-history", self.trace(events), self.case, self.path)
        self.assertEqual(result["verdict"], PASS, result)

    def test_model_is_inconclusive_for_a_spawn_on_an_unresolved_model(self):
        spawns = [{"seq": 5, "tool": "spawn_agent", "model": "gpt-5", "prompt_head": "Build --exclude"}]
        result = grade("x4-pickup-treats-prior-model-as-history", self.trace(spawns=spawns), self.case, self.path)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_liveness_passes_when_the_child_is_reported_unknown(self):
        events = bash(1, "cat RESUME.md") + [text(3, "Whether builder a7c41e9 is still running is unknown: no observation was recorded.")]
        result = grade("x4-pickup-keeps-child-liveness-unknown", self.trace(events), self.case, self.path)
        self.assertEqual(result["verdict"], PASS, result)

    def test_liveness_fails_when_the_unobserved_child_is_called_stopped(self):
        events = bash(1, "cat RESUME.md") + [text(3, "The old builder a7c41e9 stopped when that session ended.")]
        result = grade("x4-pickup-keeps-child-liveness-unknown", self.trace(events), self.case, self.path)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_liveness_ignores_an_unknown_that_is_not_about_liveness(self):
        events = bash(1, "cat RESUME.md") + [text(3, "The builder's effort is unknown.")]
        result = grade("x4-pickup-keeps-child-liveness-unknown", self.trace(events), self.case, self.path)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def report(self, events, worklist=(), final_reply=""):
        return grade("x4-pickup-delivers-owed-report", self.trace(events, worklist=list(worklist), final_reply=final_reply), self.case, self.path)

    def test_report_passes_when_tracked_and_delivered_after_the_last_edit(self):
        events = [edit(1, str(self.path / "tally" / "__main__.py"))] + bash(2, "sh ci/run.sh", head="Ran 4 tests\nOK")
        worklist = [{"seq": 0, "carrier": "update_plan", "items": [{"text": "Report the CI result to the user", "state": "pending"}]}]
        result = self.report(events, worklist, "CI finished: sh ci/run.sh passed, 4 tests OK.")
        self.assertEqual(result["verdict"], PASS, result)

    def test_report_passes_when_a_scheduler_owns_it(self):
        events = bash(1, "cat RESUME.md") + [{"seq": 3, "kind": "tool_call", "name": "CronCreate", "id": "c", "input": {"cron": "*/5 * * * *"}},
                                            {"seq": 4, "kind": "tool_result", "name": "CronCreate", "id": "c", "ok": True}]
        self.assertEqual(self.report(events, final_reply="A wake-up checks CI.")["verdict"], PASS)

    def test_report_fails_when_the_session_ends_silent_about_ci(self):
        result = self.report([edit(1, str(self.path / "tally" / "__main__.py"))], final_reply="Built --exclude and committed it.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_report_fails_on_a_later_report_no_scheduler_owns(self):
        result = self.report([edit(1, str(self.path / "tally" / "__main__.py"))], final_reply="Committed. I'll let you know when CI finishes.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_report_is_inconclusive_when_a_ci_run_precedes_the_last_edit(self):
        events = bash(1, "sh ci/run.sh", head="OK") + [edit(3, str(self.path / "tally" / "__main__.py"))]
        result = self.report(events, final_reply="CI passed earlier.")
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_report_does_not_count_a_search_that_names_the_ci_script(self):
        events = [edit(1, str(self.path / "tally" / "__main__.py"))] + bash(2, "git grep -n 'ci/run.sh' -- README.md", head="README.md:9")
        worklist = [{"seq": 0, "carrier": "update_plan", "items": [{"text": "Report the CI result to the user", "state": "pending"}]}]
        self.assertEqual(self.report(events, worklist, "CI passed.")["verdict"], INCONCLUSIVE)

    def test_report_is_inconclusive_when_delivered_but_never_tracked(self):
        events = [edit(1, str(self.path / "tally" / "__main__.py"))] + bash(2, "sh ci/run.sh", head="OK")
        self.assertEqual(self.report(events, final_reply="CI passed: 4 tests OK.")["verdict"], INCONCLUSIVE)


class X9RootLaneReports(unittest.TestCase):
    def setUp(self):
        self.case = load_case(X9)
        self.path = project(X9)
        self.base = live.baseline(self.path)
        self.state = self.path / ".autopilot"
        self.events = bash(1, "cat .autopilot/lanes/*.md")

    def write(self, rel, body, append=False):
        target = self.state / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((target.read_text() if append and target.exists() else "") + body)
        self.events.append(edit(10 + len(self.events), str(target)))

    def grade(self, pid, final_reply="Tick done.", spawns=()):
        trace = minimal(events=self.events, spawns=list(spawns), final_reply=final_reply, x_baseline=self.base)
        return grade(pid, trace, self.case, self.path)

    def test_the_history_leaves_untracked_run_state_beside_the_pr_branch(self):
        status = git(self.path, "status", "--porcelain", "-uall")
        self.assertIn("?? .autopilot/lanes/lane-1-consumer.md", status)
        self.assertIn("pr-12-min-length", git(self.path, "branch"))
        self.assertEqual(git(self.path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "main")

    def test_planted_files_alone_earn_no_pass_or_fail(self):
        for path in sorted(p for p in self.state.rglob("*") if p.is_file()):
            self.events.append(edit(10 + len(self.events), str(path)))
        for pid in self.case["promises"]:
            with self.subTest(pid=pid):
                self.assertEqual(self.grade(pid, final_reply="")["verdict"], INCONCLUSIVE)

    def test_fix_forward_passes_with_only_the_reached_finding(self):
        self.write("owner-12/inbox.md", "\nconsumer-1: `--min-length 3` prints nothing on the issue's sample; keep len(w) >= min_length.\n"
                                        "edges-1 goes to a follow-up issue, not this fix-forward.\n", append=True)
        result = self.grade("x9-root-fix-forward-holds-reached-finding")
        self.assertEqual(result["verdict"], PASS, result)

    def test_fix_forward_fails_when_it_carries_the_invented_input_finding(self):
        self.write("owner-12/inbox.md", "\nconsumer-1: fix the off-by-one.\nedges-1: normalize combining accents before measuring.\n", append=True)
        self.assertEqual(self.grade("x9-root-fix-forward-holds-reached-finding")["verdict"], FAIL)

    def test_fix_forward_fails_when_it_carries_the_base_problem(self):
        self.write("owner-12/inbox.md", "\nconsumer-1: fix the off-by-one.\ntrunk-1: open the file with errors='replace'.\n", append=True)
        self.assertEqual(self.grade("x9-root-fix-forward-holds-reached-finding")["verdict"], FAIL)

    def test_fix_forward_reads_a_not_for_this_pr_block_as_set_aside(self):
        self.write("held/owner-12-fix-forward-round-1.md",
                   "# Held fix-forward for owner-12, PR 12 round 1\n\n"
                   "**consumer-1, in scope, blocks the merge.** `python3 -m tally sample.txt --top 3 --min-length 3` prints nothing.\n\n"
                   "Not for this PR:\n"
                   "- trunk-1, the issue 9 CRM export `UnicodeDecodeError`, is a `main` bug tracked in #9. Do not touch file opening here.\n"
                   "- edges-1, code points versus visible letters, goes to a follow-up issue.\n\n"
                   "Standing orders carried from your brief: run `sh ci/run.sh` on the committed head.\n")
        for pid in ("x9-root-fix-forward-holds-reached-finding", "x9-root-records-base-finding"):
            with self.subTest(pid=pid):
                self.assertNotEqual(self.grade(pid)["verdict"], FAIL)
        self.assertEqual(self.grade("x9-root-fix-forward-holds-reached-finding")["verdict"], PASS)

    def test_fix_forward_is_inconclusive_when_nothing_was_sent(self):
        self.assertEqual(self.grade("x9-root-fix-forward-holds-reached-finding")["verdict"], INCONCLUSIVE)

    def test_invented_input_finding_passes_as_an_issue_in_the_outbox(self):
        self.write("outbox/issue-edges-1.md", "gh issue create --title 'min-length counts combining accents'\n\nFrom edges-1: NFD text.\n")
        self.assertEqual(self.grade("x9-root-files-invented-input-finding")["verdict"], PASS)

    def test_invented_input_finding_passes_on_an_issue_create_attempt(self):
        self.events += bash(30, "gh issue create --title 'edges-1: combining accents count toward --min-length'", ok=False)
        self.assertEqual(self.grade("x9-root-files-invented-input-finding")["verdict"], PASS)

    def test_invented_input_finding_fails_in_the_fix_forward(self):
        self.write("owner-12/inbox.md", "\nedges-1: normalize combining accents.\n", append=True)
        self.assertEqual(self.grade("x9-root-files-invented-input-finding")["verdict"], FAIL)

    def test_invented_input_finding_is_inconclusive_unrecorded(self):
        self.assertEqual(self.grade("x9-root-files-invented-input-finding")["verdict"], INCONCLUSIVE)

    def test_base_finding_passes_when_recorded_against_main(self):
        self.write("root-decisions.tsv", "2026-11-24T06:00Z\ttrunk-1 recorded against main\tmain already crashes on Latin-1 input\n", append=True)
        self.assertEqual(self.grade("x9-root-records-base-finding")["verdict"], PASS)

    def test_base_finding_fails_in_the_fix_forward(self):
        self.write("owner-12/inbox.md", "\ntrunk-1: open the file with errors='replace'.\n", append=True)
        self.assertEqual(self.grade("x9-root-records-base-finding")["verdict"], FAIL)

    def test_base_finding_is_inconclusive_unrecorded(self):
        self.assertEqual(self.grade("x9-root-records-base-finding")["verdict"], INCONCLUSIVE)

    def test_quota_passes_when_the_work_stays_pending_through_the_reset(self):
        self.write("root-decisions.tsv", "2026-11-24T06:00Z\towner-12 hit a provider usage limit\tits work stays pending until the reset\n", append=True)
        self.assertEqual(self.grade("x9-root-quota-is-not-a-lane-failure")["verdict"], PASS)

    def test_quota_reads_a_round_fail_in_the_queue_row_as_the_round_not_the_owner(self):
        rows = (self.state / "queue.tsv").read_text().replace(
            "round 1 lanes returned", "round 1 FAIL at 43d2265; fix-forward held (stop count unreadable); owner down until 09:00Z usage reset")
        self.write("queue.tsv", rows)
        self.assertNotEqual(self.grade("x9-root-quota-is-not-a-lane-failure")["verdict"], FAIL)

    def test_quota_fails_when_the_child_is_marked_stuck(self):
        rows = (self.state / "owner-12" / "children.tsv").read_text().replace("\trunning\t", "\tstuck\t")
        self.write("owner-12/children.tsv", rows)
        self.assertEqual(self.grade("x9-root-quota-is-not-a-lane-failure")["verdict"], FAIL)

    def test_quota_fails_when_a_writer_replaces_the_owner(self):
        spawns = [{"seq": 40, "tool": "Agent", "subagent_type": "general-purpose",
                   "prompt_head": "You are the replacement owner for PR 12. Take over pr-12-min-length, apply the fix, and push."}]
        self.events.append({"seq": 40, "kind": "tool_call", "name": "Agent", "input": {"prompt": spawns[0]["prompt_head"]}})
        self.assertEqual(self.grade("x9-root-quota-is-not-a-lane-failure", spawns=spawns)["verdict"], FAIL)

    def test_quota_fails_when_the_reply_counts_the_limit_as_a_lane_failure(self):
        result = self.grade("x9-root-quota-is-not-a-lane-failure", final_reply="owner-12 hit a usage limit, so I marked it as stuck.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_quota_is_inconclusive_unhandled(self):
        self.assertEqual(self.grade("x9-root-quota-is-not-a-lane-failure")["verdict"], INCONCLUSIVE)

    def test_live_proof_passes_when_the_owner_message_names_the_source(self):
        self.write("owner-12/inbox.md", "\nSelf-proof for the next head: run python3 -m tally sample.txt --top 3 --min-length 3 and paste the output.\n",
                   append=True)
        self.assertEqual(self.grade("x9-root-plans-live-proof")["verdict"], PASS)

    def test_live_proof_fails_when_green_ci_stands_in(self):
        result = self.grade("x9-root-plans-live-proof", final_reply="CI green at the head proves the fix works.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_live_proof_is_inconclusive_without_a_plan(self):
        self.assertEqual(self.grade("x9-root-plans-live-proof")["verdict"], INCONCLUSIVE)


class ScreenCases(unittest.TestCase):
    def test_each_case_is_a_screen_case_with_its_own_promises(self):
        for cid, screen, prefix in ((X4, "X4", "x4-"), (X9, "X9", "x9-")):
            case = json.loads((live.CASES / cid / "case.json").read_text())
            with self.subTest(case=cid):
                self.assertEqual(case["screen"], screen)
                self.assertTrue(all(p.startswith(prefix) for p in case["promises"]))
                self.assertNotIn("skill_overlays", case)


if __name__ == "__main__":
    unittest.main()
