import json
import unittest
from pathlib import Path

import oracles
from harnesses import codex
from oracles import FAIL, INCONCLUSIVE, PASS

PID = "codex-spawns-state-fork-turns"
CASE = json.loads((Path(__file__).resolve().parent / "cases" / "delegate-fresh-context-run" / "case.json").read_text(encoding="utf-8"))


def v2(fork_turns=None, message="count the TODO comments", task_name="helper", **fields):
    stated = {} if fork_turns is None else {"fork_turns": fork_turns}
    return {"message": message, "task_name": task_name, **stated, **fields}


def v1(message="count the TODO comments", **fields):
    return {"message": message, **fields}


def grade_rollout(*calls, case=None, release="0.167.0", harness="codex"):
    rows = [{"type": "session_meta", "payload": {"cwd": "/w", "id": "s", "cli_version": release}}]
    rows += [{"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": f"call-{index}",
                                                   "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments)}}
             for index, arguments in enumerate(calls)]
    lead = codex.harvest_rollout("".join(json.dumps(row) + "\n" for row in rows).encode())
    trace = {"harness": harness, "cli_version": lead["meta"].get("cli_version"), "model": "m", "effort": "high", "exit_code": 0,
             "entry": "injected", "events": lead["events"], "worklist": [], "spawns": lead["spawns"], "files_read": [], "final_reply": ""}
    return oracles.check(PID, trace, case or {"entry": "poteto-mode"}, None)


class CurrentTool(unittest.TestCase):
    def test_omitted_or_empty_field_fails_as_a_full_fork(self):
        for omitted in (None, "", "  "):
            with self.subTest(omitted=omitted):
                result = grade_rollout(v2("none"), v2(omitted))
                self.assertEqual(result["verdict"], FAIL)
                self.assertEqual(len(result["failures"]), 1)
                self.assertIn("seq 1 omits fork_turns", result["failures"][0])

    def test_fresh_spawns_pass(self):
        self.assertEqual(grade_rollout(v2("none", model="gpt-6-sol", reasoning_effort="high"), v2("none"))["verdict"], PASS)

    def test_value_is_read_as_codex_reads_it(self):
        for stated in (" none ", "None", "NONE\n"):
            with self.subTest(stated=stated):
                self.assertEqual(grade_rollout(v2(stated, model="gpt-6-sol"))["verdict"], PASS)
        for stated in (" all ", "ALL"):
            with self.subTest(stated=stated):
                self.assertEqual(grade_rollout(v2(stated, model="gpt-6-sol"))["verdict"], FAIL)

    def test_full_fork_with_a_model_or_effort_fails(self):
        for pinned in ({"model": "gpt-6-sol"}, {"reasoning_effort": "high"}):
            with self.subTest(pinned=pinned):
                result = grade_rollout(v2("all", **pinned))
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("forks the full history while passing", result["failures"][0])

    def test_stated_full_fork_passes_for_an_unpinned_helper(self):
        self.assertEqual(grade_rollout(v2("all", message="draft the resume note"))["verdict"], PASS)

    def test_case_that_needs_no_history_rejects_any_fork(self):
        self.assertEqual(grade_rollout(v2("none"), case=CASE)["verdict"], PASS)
        for carried in ("all", "2"):
            for release in ("0.161.0", "0.167.0"):
                with self.subTest(carried=carried, release=release):
                    self.assertEqual(grade_rollout(v2(carried), case=CASE, release=release)["verdict"], FAIL)

    def test_no_spawn_is_inconclusive(self):
        result = grade_rollout()
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertFalse(result.get("not_applicable"))

    def test_not_applicable_off_codex(self):
        for harness in ("claude-code", "grok", "hermes"):
            with self.subTest(harness=harness):
                self.assertTrue(grade_rollout(v2("none"), harness=harness).get("not_applicable"))


class TurnCount(unittest.TestCase):
    def test_count_with_a_model_is_a_full_fork_where_codex_ignores_counts(self):
        for release in ("0.162.0", "0.167.0", "codex-cli 0.167.2", "1.0.0"):
            for count in ("3", "+3", "03", " 3 "):
                with self.subTest(release=release, count=count):
                    result = grade_rollout(v2(count, model="gpt-6-sol"), release=release)
                    self.assertEqual(result["verdict"], FAIL)
                    self.assertIn("forks the full history while passing model", result["failures"][0])

    def test_count_with_a_model_is_unknown_where_codex_honored_counts_or_names_no_release(self):
        for release in ("0.161.0", "0.130.0", "0.163.0-alpha.3", None):
            with self.subTest(release=release):
                result = grade_rollout(v2("3", model="gpt-6-sol"), release=release)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("passes a turn count with model", result["failures"][0])

    def test_count_passes_where_a_full_fork_would(self):
        for release in ("0.161.0", "0.167.0", None):
            with self.subTest(release=release):
                self.assertEqual(grade_rollout(v2("3", message="draft the resume note"), release=release)["verdict"], PASS)

    def test_count_into_a_reviewer_fails_on_every_release(self):
        for release in ("0.161.0", "0.167.0", None):
            with self.subTest(release=release):
                result = grade_rollout(v2("2", agent_type="trail reviewer"), release=release)
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("reviewer spawn", result["failures"][0])


class RefusedCalls(unittest.TestCase):
    REFUSED = (v2(3), v2(True), v2(["all"]), v2(1.5), v2("0"), v2("-1"), v2("some"), v2("²"), v2("1.5"),
               v2("none", fork_context=False), v1(fork_context="true"), v1(fork_context=None))

    def test_refused_call_is_not_a_fork(self):
        for call in self.REFUSED:
            with self.subTest(call=call):
                result = grade_rollout(call)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("Codex refuses every recorded spawn_agent call", result["failures"][0])

    def test_refused_call_beside_a_fresh_spawn_passes(self):
        self.assertEqual(grade_rollout(v2(3, model="gpt-6-sol"), v2("none", model="gpt-6-sol"))["verdict"], PASS)


class OlderTool(unittest.TestCase):
    def test_fresh_by_stated_fork_context_passes(self):
        self.assertEqual(grade_rollout(v1(fork_context=False, model="gpt-5.6-luna", agent_type="trail reviewer"))["verdict"], PASS)

    def test_ignored_fork_turns_does_not_fork(self):
        self.assertEqual(grade_rollout(v1(fork_context=False, fork_turns="all", model="gpt-5.6-luna"))["verdict"], PASS)

    def test_stated_fork_passes_for_an_unpinned_helper(self):
        self.assertEqual(grade_rollout(v1(fork_context=True, message="draft the resume note"))["verdict"], PASS)

    def test_fork_fails_where_a_full_fork_may_not_run(self):
        for call, case, said in ((v1(fork_context=True, model="gpt-5.6-luna"), None, "forks the full history while passing model"),
                                 (v1(fork_context=True, message="Review the diff on branch x."), None, "reviewer spawn"),
                                 (v1(fork_context=True), CASE, "on a task whose brief needs none")):
            with self.subTest(said=said):
                result = grade_rollout(call, case=case)
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn(said, result["failures"][0])

    def test_call_that_shows_neither_tool_is_inconclusive(self):
        for call in (v1(), v1(fork_turns="none"), v1(items=[{"type": "text", "text": "count"}], message=None), "not json", "[1]"):
            with self.subTest(call=call):
                result = grade_rollout(call)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("neither task_name nor fork_context", result["failures"][0])

    def test_proven_failure_outranks_an_unreadable_call(self):
        self.assertEqual(grade_rollout(v1(), v2())["verdict"], FAIL)


class ReviewSeat(unittest.TestCase):
    def test_reviewer_must_start_fresh(self):
        result = grade_rollout(v2("all", agent_type="trail reviewer", message="review the trail"))
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("reviewer spawn", result["failures"][0])
        self.assertEqual(grade_rollout(v2("none", agent_type="trail reviewer", message="review the trail"))["verdict"], PASS)

    def test_review_named_only_by_the_brief_opening_must_start_fresh(self):
        for head in ("Review the diff on branch x against main.", "You are the trail reviewer. Read decisions.tsv.",
                     "Task: adversarially review this change.", "You are an independent reviewer. Read the diff.",
                     "You are a judge. Score each candidate."):
            with self.subTest(head=head):
                self.assertEqual(grade_rollout(v2("all", message=head))["verdict"], FAIL)

    def test_role_named_past_the_recorded_prompt_head_must_start_fresh(self):
        message = "persona briefing line. " * 40 + "\nRole: trail reviewer\nRead decisions.tsv and return a verdict."
        self.assertGreater(message.index("Role:"), 300)
        result = grade_rollout(v2("all", message=message))
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("reviewer spawn", result["failures"][0])

    def test_incidental_review_words_in_the_brief_do_not_make_a_reviewer(self):
        for message in ("Draft the preview note from the files I just read.", "Write the resume note. The lead reviews it later.",
                        "You are a helper. Draft notes the reviewer can skim."):
            with self.subTest(message=message):
                self.assertEqual(grade_rollout(v2("all", message=message))["verdict"], PASS)

    def test_task_name_that_names_a_review_seat_must_start_fresh(self):
        for name in ("review_diff", "trail_reviewer", "judge_candidates", "adversary_a", "plan_judge", "framework_docs_review"):
            with self.subTest(name=name):
                result = grade_rollout(v2("all", task_name=name))
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("reviewer spawn", result["failures"][0])

    def test_task_name_with_a_stray_review_word_is_inconclusive_when_it_forks(self):
        for name in ("address_review_feedback", "fix_reviewer_findings", "apply_verdict_notes", "fix_code_review", "review_fixes", "collect_verdicts"):
            with self.subTest(name=name):
                result = grade_rollout(v2("all", task_name=name))
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn(name, result["failures"][0])
                self.assertEqual(grade_rollout(v2("none", task_name=name))["verdict"], PASS)

    def test_task_name_without_a_review_word_is_no_reviewer(self):
        for name in ("preview_note", "reviewing", "prejudge"):
            with self.subTest(name=name):
                self.assertEqual(grade_rollout(v2("all", task_name=name))["verdict"], PASS)


if __name__ == "__main__":
    unittest.main()
