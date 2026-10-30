import datetime
import fcntl
import hashlib
import json
import io
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from contextlib import nullcontext

import live
from grade_boundary import GradeRefused, _authorize_fixture
from harnesses.login import LoginRequired, auth_death, death_record, error_verdict

FIXTURES = Path(__file__).resolve().parent / "testdata" / "auth_death"

CODEX_CHAT = """I'm using `poteto-mode`. I'll identify the command first.

1. In progress. **You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.
2. Pending. `how` over the affected subsystem.
3. ⏭️ `architect`. skipped: one module
4. [x] Verify on the matching surface."""


class ChatWorklist(unittest.TestCase):
    def test_capitalized_states_skips_and_checkboxes_parse(self):
        items = live.chat_worklist(CODEX_CHAT)
        self.assertEqual([i["state"] for i in items], ["in progress", "pending", "skipped: one module", "completed"])
        self.assertEqual(items[1]["text"], "Pending. `how` over the affected subsystem.")

    def test_a_list_with_no_state_is_not_a_worklist(self):
        self.assertIsNone(live.chat_worklist("1. read the code\n2. write the fix"))

    def test_a_reply_summary_with_one_state_word_is_not_a_worklist(self):
        reply = "Summary\n- the flag now emits rows\n- default text stays byte-identical\n- verification done for both forms"
        self.assertIsNone(live.chat_worklist(reply))

    def test_bare_checkbox_lines_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("[x] one\n[ ] two\n- [~] three")],
                         ["completed", "pending", "in progress"])

    def test_parenthesized_state_with_an_explanation_parses(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("1. Read source (done: inspected)\n2. Run check (done: passed)")],
                         ["completed", "completed"])

    def test_parentheses_inside_a_state_explanation_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("1. Fix parser (done: checked parse())\n2. Run tests (done: 3 cases (all passed))")],
                         ["completed", "completed"])

    def test_underscore_italic_state_annotations_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("1. Read source _(done: inspected)_\n2. Run check _(done: passed)_")],
                         ["completed", "completed"])

    def test_emphasized_done_and_blocked_annotations_parse(self):
        reply = ("4. Delegate code-writing on the `feature` role. *(done: commit `3f31bec`, reviewed by me)*\n"
                 "8. Opening a PR. *(blocked: `git remote -v` is empty)*")
        self.assertEqual([i["state"] for i in live.chat_worklist(reply)], ["completed", "blocked"])

    def test_a_mid_sentence_state_word_with_a_colon_is_not_a_state(self):
        self.assertIsNone(live.chat_worklist("1. Mark it done: later\n2. Note the pending: queue"))

    def test_prose_lists_that_mention_blocked_or_call_signatures_are_not_worklists(self):
        for reply in ("The sandbox rules:\n- Network access is blocked.\n- Writes outside the project are blocked.",
                      "Notes:\n- Blocked users cannot log in\n- Blocked IPs are listed in the config",
                      "API:\n1. Call run(done: bool)\n2. Call stop(pending: int)",
                      "1. Use run(done: true)\n2. Use stop(pending: false)"):
            with self.subTest(reply=reply):
                self.assertIsNone(live.chat_worklist(reply))

    def test_leading_state_labels_and_trailing_complete_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("- Done: wrote the parser\n- Blocked: no creds for CI\n- Pending: docs")],
                         ["completed", "blocked", "pending"])
        self.assertEqual([i["state"] for i in live.chat_worklist("Status:\n- The migration is complete.\n- The rollout is complete.")],
                         ["completed", "completed"])

    def test_a_long_item_of_repeated_annotations_parses_in_linear_time(self):
        item = "1. text " + "(done: x) " * 40000 + "tail"
        for reply, states in ((item + "\n2. (done: y)", None), (item + " (done: z)\n2. (done: y)", ["completed", "completed"])):
            started = time.perf_counter()
            worklist = live.chat_worklist(reply)
            elapsed = time.perf_counter() - started
            with self.subTest(states=states):
                self.assertEqual(worklist and [i["state"] for i in worklist], states)
                self.assertLess(elapsed, 2)

    def test_a_long_run_of_separators_before_a_trailing_state_parses_in_linear_time(self):
        for separator in (" ", "-", "*", "(", "_", "["):
            for tail, states in (("x", None), ("done", ["completed", "completed"])):
                reply = "1. text" + separator * 40000 + tail + "\n2. (done: y)"
                started = time.perf_counter()
                worklist = live.chat_worklist(reply)
                elapsed = time.perf_counter() - started
                with self.subTest(separator=separator, tail=tail):
                    self.assertEqual(worklist and [i["state"] for i in worklist], states)
                    self.assertLess(elapsed, 2)


class Custody(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-live-custody-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.canary = self.tmp / "canary.txt"
        self.canary.write_bytes(b"CANARY\n")
        self.ran = self.tmp / "ran"
        self.argv = ["/bin/sh", "-c", f"echo out; echo err >&2; touch {self.ran}"]

    def test_execute_refuses_a_planted_stream_link_without_writing_through_it(self):
        for name, target in (("stdout", self.canary), ("stderr", self.canary), ("stdout", self.tmp / "missing")):
            with self.subTest(name=name, target=target.name):
                streams = self.tmp / f"streams-{name}-{target.name}"
                streams.mkdir()
                paths = {"stdout": streams / "turn-1.jsonl", "stderr": streams / "turn-1.err"}
                paths[name].symlink_to(target)
                with self.assertRaises(GradeRefused) as refused:
                    live.execute(self.argv, self.tmp, {}, 5, paths["stdout"], paths["stderr"])
                self.assertEqual((refused.exception.receipt["reason"], self.canary.read_bytes(), self.ran.exists(),
                                  (self.tmp / "missing").exists()), ("output_unsafe", b"CANARY\n", False, False))

    def test_execute_refuses_a_linked_stream_directory_without_creating_outside(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.tmp / "transcripts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(GradeRefused):
            live.execute(self.argv, self.tmp, {}, 5, self.tmp / "transcripts" / "turn-0.jsonl",
                         self.tmp / "transcripts" / "turn-0.err")
        self.assertEqual((list(outside.iterdir()), self.ran.exists()), ([], False))

    def test_execute_captures_both_streams_in_fresh_files(self):
        record = live.execute(self.argv, self.tmp, {}, 5, self.tmp / "turn-0.jsonl", self.tmp / "turn-0.err")
        self.assertEqual((record["exit_code"], (self.tmp / "turn-0.jsonl").read_bytes(), (self.tmp / "turn-0.err").read_bytes()),
                         (0, b"out\n", b"err\n"))

    def test_fixture_lock_refuses_a_planted_link_without_truncating_its_target(self):
        for target in (self.canary, self.tmp / "missing"):
            with self.subTest(target=target.name):
                lock = self.tmp / "pstack-live-fx.lock"
                lock.unlink(missing_ok=True)
                lock.symlink_to(target)
                with mock.patch.object(live.tempfile, "gettempdir", return_value=str(self.tmp)), \
                        self.assertRaises(OSError):
                    live.fixture_lock("fx").close()
                self.assertEqual((self.canary.read_bytes(), (self.tmp / "missing").exists()), (b"CANARY\n", False))

    def test_fixture_lock_excludes_a_second_holder(self):
        with mock.patch.object(live.tempfile, "gettempdir", return_value=str(self.tmp)):
            held = live.fixture_lock("fx")
            try:
                with open(self.tmp / "pstack-live-fx.lock", "rb") as other, self.assertRaises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                held.close()


class FixtureCommits(unittest.TestCase):
    def test_commits_ignore_the_contributors_signing_and_hook_settings(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            tmp = Path(tmp)
            hooks = tmp / "hooks"
            hooks.mkdir()
            (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
            (hooks / "pre-commit").chmod(0o755)
            config = tmp / "gitconfig"
            config.write_text(f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /usr/bin/false\n[core]\n\thooksPath = {hooks}\n"
                              "[user]\n\tname = Someone Else\n\temail = someone@example.org\n")
            case = {"fixture": "relay", "history": "relay-retry-limit"}
            dest = tmp / "project"
            with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
                live.make_project(case, dest)
            log = subprocess.run(["git", "-C", str(dest), "log", "--format=%an <%ae>"], capture_output=True, text=True,
                                 env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}).stdout.split("\n")
            self.assertEqual({line for line in log if line}, {"dev <dev@example.com>"})
            self.assertGreater(len([line for line in log if line]), 1)


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class GradeRun(unittest.TestCase):
    def test_run_case_grades_actual_codex_and_grok_harvests_without_model_turns(self):
        case = live.load_case("principle-steer-run")
        case["turns"] = ["first prompt", "second prompt"]
        case["tmp_lock"] = False
        retained = os.environ.get("PSTACK_GRADE_TEST_ARTIFACTS")
        temporary = nullcontext(tempfile.mkdtemp(prefix="pstack-live-harvest-", dir=retained)) if retained else \
                    tempfile.TemporaryDirectory(prefix="pstack-live-harvest-")
        with temporary as tmp:
            out = Path(tmp).resolve()
            for harness in ("codex", "grok"):
                with self.subTest(harness=harness):
                    module = live.adapter(harness)

                    def prepare(run):
                        (run.root / "launch.json").write_text(json.dumps({"path": "synthetic-no-model",
                            "source": "test", "version": "test", "rejected": []}))

                    def turn(run, text, index):
                        (run.root / f"turn-{index}.jsonl").write_bytes(b"")
                        return {"index": index, "session_id": "owned-session", "argv": [harness, text],
                            "exit_code": 0 if index == 0 else -9, "timed_out": index == 1, "duration_s": 0.25,
                            "stream": str(run.root / f"turn-{index}.jsonl"), "stderr": str(run.root / f"turn-{index}.err"),
                            f"{harness}_bin": "synthetic-no-model", f"{harness}_bin_source": "test",
                            **({"last_message": str(run.root / "last.txt")} if harness == "codex" else {})}

                    output = io.StringIO()
                    with mock.patch.object(live, "load_case", return_value=case), \
                         mock.patch.object(module, "prepare", side_effect=prepare), \
                         mock.patch.object(module, "turn", side_effect=turn), redirect_stdout(output):
                        root = Path(live.run_case(harness, case["id"], "HEAD", out, 0)["run"])
                    trace = json.loads((root / "trace.json").read_text())
                    record = json.loads((root / "run.json").read_text())
                    self.assertEqual(trace["x_turns"], [
                        {"index": 0, "session_id": "owned-session", "argv": [harness, "first prompt"],
                         "exit_code": 0, "timed_out": False, "duration_s": 0.25},
                        {"index": 1, "session_id": "owned-session", "argv": [harness, "second prompt"],
                         "exit_code": -9, "timed_out": True, "duration_s": 0.25}])
                    self.assertIn("stream", record["turns"][0])
                    self.assertEqual(len(json.loads(output.getvalue())["authorization_id"]), 32)
                    verdict = json.loads((root / "verdict.json").read_text())
                    self.assertEqual({p["verdict"] for p in verdict["promises"].values()}, {"INCONCLUSIVE"})

    def test_an_overlaid_arm_with_run_overrides_passes_parent_grading_admission(self):
        from harnesses import codex
        case = live.load_case("deslop-handoff")
        case["skill_overlays"] = [
            {"file": "no-comments/agents/openai.yaml", "old": "policy:\n  allow_implicit_invocation: false\n",
             "new": 'policy: {allow_implicit_invocation: "false"}\n'},
            {"file": "arena/agents/openai.yaml", "old": "policy:\n  allow_implicit_invocation: false\n",
             "new": "policy:\n  allow_implicit_invocation: 'false'\n"},
            {"file": "bro/agents/openai.yaml", "old": "policy:\n  allow_implicit_invocation: false\n",
             "new": "interface:\n  allow_implicit_invocation: false\n"},
        ]
        with tempfile.TemporaryDirectory(prefix="pstack-live-arm-") as tmp:
            out = Path(tmp).resolve()

            def prepare(run):
                (run.root / "launch.json").write_text(json.dumps({"path": "synthetic-no-model", "source": "test", "version": "test", "rejected": []}))

            def turn(run, text, index):
                (run.root / "turn-0.jsonl").write_bytes(b"")
                return {"index": index, "session_id": "owned-session", "argv": ["codex", "exec", *codex.config_flags(run), text],
                        "exit_code": 0, "timed_out": False, "duration_s": 0.25, "stream": str(run.root / "turn-0.jsonl"),
                        "stderr": str(run.root / "turn-0.err"), "last_message": str(run.root / "last.txt"),
                        "codex_bin": "synthetic-no-model", "codex_bin_source": "test"}

            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(codex, "prepare", side_effect=prepare), \
                    mock.patch.object(codex, "turn", side_effect=turn), redirect_stdout(io.StringIO()):
                root = Path(live.run_case("codex", case["id"], "HEAD", out, 0, model="gpt-6-luna", effort="xhigh")["run"])
            installed = (root / "w" / "rollup" / ".agents/skills/deslop/SKILL.md").read_text()
            trace = json.loads((root / "trace.json").read_text())
            record = json.loads((root / "run.json").read_text())
            verdict = json.loads((root / "verdict.json").read_text())
        self.assertEqual(installed.count("Use the **no-comments** skill on those comments."), 1)
        self.assertNotIn("go to `/no-comments`.", installed)
        self.assertIn("no-comments", trace["x_implicit_off"])
        self.assertIn("arena", trace["x_implicit_off"])
        self.assertNotIn("bro", trace["x_implicit_off"])
        self.assertNotIn("deslop", trace["x_implicit_off"])
        self.assertIn('model="gpt-6-luna"', trace["x_turns"][0]["argv"])
        self.assertIn('model_reasoning_effort="xhigh"', trace["x_turns"][0]["argv"])
        self.assertEqual(sorted(record), ["baseline", "case", "harness", "project", "skills_at", "timeout_s", "turns"])
        self.assertEqual(verdict["promises"]["deslop-hands-unsettled-comments-to-no-comments"]["failures"], ["deslop never loaded"])

    def test_a_run_with_host_skill_hits_writes_inconclusive_for_every_promise(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            root = Path(tmp).resolve()
            case = live.load_case("feature-run")
            trace = {"harness": "claude-code", "model": "m", "exit_code": 0, "events": [], "worklist": [], "spawns": [],
                     "files_read": [], "final_reply": "done", "x_host_skill_hits": ["/Users/someone/.claude/skills"]}
            (root / "run.json").write_text(json.dumps({"harness": "claude-code", "case": case["id"], "skills_at": "x", "project": str(root / "p")}))
            (root / "trace.json").write_text(json.dumps(trace))
            authority = _authorize_fixture(root, root / "p", case, json.loads((root / "run.json").read_text()), trace)
            graded = live.grade(authority)
            self.assertEqual({r["verdict"] for r in graded["promises"].values()}, {"INCONCLUSIVE"})
            self.assertEqual(set(graded["promises"]), set(case["promises"]))
            self.assertEqual(json.loads((root / "verdict.json").read_text()), graded)

    def test_a_run_with_a_clean_turn_is_graded_even_when_the_trace_carries_only_the_last_exit_code(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            root = Path(tmp).resolve()
            case = live.load_case("principle-steer-run")
            trace = {"harness": "claude-code", "model": "m", "exit_code": 1, "events": [{"seq": 0, "kind": "text", "text": "Done."}],
                     "worklist": [], "spawns": [], "files_read": [], "final_reply": "Done."}
            run = {"harness": "claude-code", "case": case["id"], "skills_at": "x", "project": str(root / "p"),
                   "turns": [{"exit_code": 0}, {"exit_code": 1}]}
            (root / "run.json").write_text(json.dumps(run))
            (root / "trace.json").write_text(json.dumps(trace))
            authority = _authorize_fixture(root, root / "p", case, json.loads((root / "run.json").read_text()), trace)
            graded = live.grade(authority)
            self.assertNotIn("never started", json.dumps(graded))



DESLOP_STEP_5 = "Comments the rules below do not settle go to `/no-comments`."


def synthetic_turns(harness, during_turn=lambda run, index: None):
    """prepare and turn stand-ins that write empty owned streams, so run_case harvests and grades with no model."""
    def prepare(run):
        (run.root / "launch.json").write_text(json.dumps({"path": "synthetic-no-model", "source": "test", "version": "test", "rejected": []}))

    def turn(run, text, index):
        during_turn(run, index)
        (run.root / f"turn-{index}.jsonl").write_bytes(b"")
        return {"index": index, "session_id": "owned-session", "argv": [harness, text], "exit_code": 0, "timed_out": False,
                "duration_s": 0.25, "stream": str(run.root / f"turn-{index}.jsonl"), "stderr": str(run.root / f"turn-{index}.err"),
                f"{harness}_bin": "synthetic-no-model", f"{harness}_bin_source": "test",
                **({"last_message": str(run.root / "last.txt")} if harness == "codex" else {})}
    return prepare, turn


def steer_case():
    case = live.load_case("principle-steer-run")
    case["turns"] = ["go"]
    case["tmp_lock"] = False
    return case


def add_worktree(run, path):
    live.git_run(run.project, "worktree", "add", "-q", "-b", f"candidate-{path.name}", str(path))


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class ScratchWorktrees(unittest.TestCase):
    def test_a_worktree_the_agent_adds_under_the_run_tmpdir_is_graded(self):
        case = steer_case()
        with tempfile.TemporaryDirectory(prefix="pstack-live-scratch-") as tmp:
            out = Path(tmp).resolve()
            for harness in ("codex", "grok"):
                with self.subTest(harness=harness):
                    module = live.adapter(harness)
                    prepare, turn = synthetic_turns(harness, lambda run, index: add_worktree(
                        run, run.root / "tmp" / "arena-tally-json.yq6S6F" / "candidate-2"))
                    output = io.StringIO()
                    with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(module, "prepare", side_effect=prepare), \
                            mock.patch.object(module, "turn", side_effect=turn), redirect_stdout(output):
                        screen = live.run_case(harness, case["id"], "HEAD", out, 0)
                    self.assertEqual(json.loads(output.getvalue()), screen)
                    self.assertNotIn("refusal", screen)
                    self.assertEqual(set(screen["verdicts"]), set(case["promises"]))
                    self.assertTrue((Path(screen["run"]) / "tmp/arena-tally-json.yq6S6F/candidate-2/.git").is_file())

    def test_a_worktree_hermes_adds_under_its_write_safe_profile_cache_is_graded(self):
        from test_hermes_evidence import _OwnerFixture
        from harnesses import hermes
        from test_hermes import HermesDatabase
        fixture = _OwnerFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        case = live.load_case("principle-steer-run")
        case["turns"] = ["go"]
        case["entry"] = None
        original_turn = hermes.turn
        candidates = []

        def turn(run, text, index):
            record = original_turn(run, text, index)
            [argv] = [argv for argv, *_ in fixture.calls[-3:] if any(a.startswith("HERMES_WRITE_SAFE_ROOT=") for a in argv)]
            safe = next(a for a in argv if a.startswith("HERMES_WRITE_SAFE_ROOT=")).split("=", 1)[1].split(":")
            self.assertEqual(safe[0], str(run.project))
            candidates.append(Path(safe[1]) / "scratch" / "tally-architect-arena" / "candidate-2")
            add_worktree(run, candidates[-1])
            db = HermesDatabase(hermes.profile(run) / "state.db")
            db.session("root")
            db.con.execute("update sessions set cwd=?", (str(run.project),))
            db.message("root", "user", "go")
            db.message("root", "assistant", "owned CLI reply")
            db.done()
            return record

        output = io.StringIO()
        with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(hermes, "turn", turn), redirect_stdout(output):
            result = live.main(["run", "--harness", "hermes", "--case", case["id"], "--out", str(fixture.base / "scratch-runs"),
                                "--hermes-retain-out", str(fixture.base / "scratch-retained")])
        screen = json.loads(output.getvalue())
        self.assertEqual((result, "refusal" in screen), (0, False))
        self.assertEqual(set(screen["verdicts"]), set(case["promises"]))
        self.assertTrue((candidates[0] / ".git").is_file())


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class BootstrapDependencies(unittest.TestCase):
    def test_a_project_deleted_during_the_turn_reaches_grading(self):
        import shutil
        case = steer_case()
        module = live.adapter("codex")
        prepare, turn = synthetic_turns("codex", lambda run, index: shutil.rmtree(run.project))
        with tempfile.TemporaryDirectory(prefix="pstack-live-bootstrap-deleted-") as tmp:
            out = Path(tmp).resolve()
            output = io.StringIO()
            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(module, "prepare", side_effect=prepare), \
                    mock.patch.object(module, "turn", side_effect=turn), mock.patch.object(live, "grade", wraps=live.grade) as grade, \
                    redirect_stdout(output):
                screen = live.run_case("codex", case["id"], "HEAD", out, 0)
            grade.assert_called_once()
            self.assertEqual(json.loads(output.getvalue()), screen)
            self.assertIn("refusal", screen)
            self.assertTrue((Path(screen["run"]) / "trace.json").is_file())

    def plant(self, run, index):
        modules = run.project / live.adapter(run.harness).SKILLS_DIR / "poteto-mode" / "scripts" / "node_modules"
        (modules / "typescript" / "bin").mkdir(parents=True)
        (modules / "typescript" / "bin" / "tsc").write_text("#!/usr/bin/env node\n")
        (modules / ".bin").mkdir()
        (modules / ".bin" / "tsc").symlink_to("../typescript/bin/tsc")

    def test_the_watch_pr_bun_install_under_the_installed_skills_is_removed_before_grading(self):
        case = steer_case()
        with tempfile.TemporaryDirectory(prefix="pstack-live-bootstrap-") as tmp:
            out = Path(tmp).resolve()
            for harness in ("codex", "grok"):
                with self.subTest(harness=harness):
                    module = live.adapter(harness)
                    prepare, turn = synthetic_turns(harness, self.plant)
                    output = io.StringIO()
                    with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(module, "prepare", side_effect=prepare), \
                            mock.patch.object(module, "turn", side_effect=turn), redirect_stdout(output):
                        screen = live.run_case(harness, case["id"], "HEAD", out, 0)
                    scripts = Path(screen["run"]) / "w" / case["fixture"] / module.SKILLS_DIR / "poteto-mode" / "scripts"
                    self.assertEqual(set(screen["verdicts"]), set(case["promises"]))
                    self.assertFalse((scripts / "node_modules").exists() or (scripts / "node_modules").is_symlink())
                    self.assertTrue((scripts / "bootstrap.ts").is_file())

    def test_a_link_swapped_into_the_bootstrap_path_is_refused_without_deleting_through_it(self):
        import shutil
        case = steer_case()
        for linked in ("poteto-mode/scripts", "poteto-mode/scripts/node_modules"):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory(prefix="pstack-live-bootstrap-link-") as tmp:
                out = Path(tmp).resolve()
                outside = out.parent / f"{out.name}-outside"
                self.addCleanup(shutil.rmtree, outside, True)

                def swap(run, index):
                    (outside / "node_modules" / ".bin").mkdir(parents=True)
                    (outside / "node_modules" / ".bin" / "tsc").write_text("outside\n")
                    target = run.project / live.adapter("codex").SKILLS_DIR / linked
                    shutil.rmtree(target, ignore_errors=True)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(outside if linked.endswith("scripts") else outside / "node_modules")

                prepare, turn = synthetic_turns("codex", swap)
                with mock.patch.object(live, "load_case", return_value=case), \
                        mock.patch.object(live.adapter("codex"), "prepare", side_effect=prepare), \
                        mock.patch.object(live.adapter("codex"), "turn", side_effect=turn), redirect_stdout(io.StringIO()):
                    with self.assertRaises(GradeRefused) as refused:
                        live.run_case("codex", case["id"], "HEAD", out, 0)
                self.assertEqual(refused.exception.receipt["reason"], "unsafe_link")
                self.assertEqual(list(out.rglob("trace.json")), [])
                self.assertEqual((outside / "node_modules" / ".bin" / "tsc").read_text(), "outside\n")


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class GradeRefusalBatch(unittest.TestCase):
    def wave(self, during_turn, runs=2):
        case = steer_case()
        module = live.adapter("codex")
        prepare, turn = synthetic_turns("codex", during_turn)
        tmp = tempfile.TemporaryDirectory(prefix="pstack-live-batch-")
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name).resolve() / "runs"
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(live, "preflight"), \
                mock.patch.object(module, "prepare", side_effect=prepare), mock.patch.object(module, "turn", side_effect=turn) as turns, \
                redirect_stdout(output), redirect_stderr(errors):
            code = live.main(["run", "--harness", "codex", "--case", case["id"], "--runs", str(runs), "--out", str(out)])
        return code, turns.call_count, [json.loads(line) for line in output.getvalue().splitlines()], errors.getvalue()

    def test_a_grade_refusal_in_the_first_case_still_runs_the_second_and_exits_2(self):
        def first_run_strays(run, index):
            if not list(run.root.parent.glob("*/elsewhere")):
                add_worktree(run, run.root / "elsewhere" / "candidate-2")

        code, turns, lines, _ = self.wave(first_run_strays)
        self.assertEqual((code, turns, len(lines)), (2, 2, 2))
        refused, graded = lines
        self.assertEqual(refused["refusal"]["reason"], "unapproved_worktree")
        self.assertEqual(refused["refusal"]["run_id"], refused["authorization_id"])
        self.assertNotIn("verdicts", refused)
        self.assertEqual((graded["n"], "refusal" in graded), (1, False))
        self.assertEqual(set(graded["verdicts"]), set(live.load_case("principle-steer-run")["promises"]))

    def test_a_refused_run_stays_sealed_for_a_later_grade(self):
        code, _, [refused], _ = self.wave(lambda run, index: add_worktree(run, run.root / "elsewhere" / "candidate-2"), runs=1)
        self.assertEqual(code, 2)
        out = Path(refused["run"]).parent
        with redirect_stderr(io.StringIO()) as again:
            self.assertEqual(live.main(["grade", refused["authorization_id"], "--out", str(out)]), 2)
        self.assertEqual(json.loads(again.getvalue())["refusal"]["reason"], "unapproved_worktree")

    def test_a_grader_that_cannot_launch_stops_the_batch_after_the_first_case(self):
        import grade_boundary
        popen = subprocess.Popen

        def no_sandbox(argv, *args, **kwargs):
            if argv[0] == "/usr/bin/sandbox-exec":
                raise OSError("sandbox-exec is gone")
            return popen(argv, *args, **kwargs)

        with mock.patch.object(grade_boundary.subprocess, "Popen", side_effect=no_sandbox):
            code, turns, lines, errors = self.wave(lambda run, index: None)
        self.assertEqual((code, turns, len(lines)), (2, 1, 1))
        self.assertEqual(lines[0]["refusal"]["reason"], "boundary_unavailable")
        self.assertIn("batch stopped", errors)


class SkillOverlays(unittest.TestCase):
    def tree(self, text):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-overlay-")
        self.addCleanup(tmp.cleanup)
        skills = Path(tmp.name)
        (skills / "deslop").mkdir()
        (skills / "deslop" / "SKILL.md").write_text(text)
        return skills

    def test_an_overlay_replaces_its_sentence_once(self):
        skills = self.tree(f"5. Hand off. {DESLOP_STEP_5} Names go on.\n")
        case = {"id": "arm", "skill_overlays": [{"file": "deslop/SKILL.md", "old": DESLOP_STEP_5, "new": "Use the **no-comments** skill."}]}
        live.apply_overlays(case, skills)
        self.assertEqual((skills / "deslop" / "SKILL.md").read_text(), "5. Hand off. Use the **no-comments** skill. Names go on.\n")

    def test_an_overlay_whose_text_is_missing_or_repeated_refuses_the_run(self):
        for text, found in (("5. Hand off.\n", 0), (f"{DESLOP_STEP_5}\n{DESLOP_STEP_5}\n", 2)):
            with self.subTest(found=found):
                skills = self.tree(text)
                case = {"id": "arm", "skill_overlays": [{"file": "deslop/SKILL.md", "old": DESLOP_STEP_5, "new": "x"}]}
                with self.assertRaisesRegex(ValueError, f"occurs {found} times in deslop/SKILL.md, expected exactly once"):
                    live.apply_overlays(case, skills)
                self.assertEqual((skills / "deslop" / "SKILL.md").read_text(), text)

    def test_an_overlay_path_outside_the_skill_tree_refuses(self):
        skills = self.tree(DESLOP_STEP_5)
        for rel in ("../deslop/SKILL.md", "/etc/hosts"):
            with self.subTest(rel=rel), self.assertRaisesRegex(ValueError, "leaves the skill tree"):
                live.apply_overlays({"id": "arm", "skill_overlays": [{"file": rel, "old": "a", "new": "b"}]}, skills)


class RunOverrides(unittest.TestCase):
    def test_model_and_effort_refuse_harnesses_without_an_override(self):
        for harness in ("hermes", "grok"):
            with self.subTest(harness=harness), self.assertRaisesRegex(ValueError, "--model and --effort support claude-code, codex, not " + harness):
                live.run_case(harness, "principle-steer-run", "HEAD", Path("/unused"), 0, model="m")

    def test_the_cli_passes_model_and_effort_to_every_case(self):
        with tempfile.TemporaryDirectory(prefix="pstack-overrides-") as tmp, mock.patch.object(live, "run_case") as run_case, \
                mock.patch.object(live, "preflight"):
            live.main(["run", "--harness", "codex", "--case", "a", "--case", "b", "--model", "gpt-6-luna", "--effort", "xhigh", "--out", tmp])
        self.assertEqual([c.args[1] for c in run_case.call_args_list], ["a", "b"])
        self.assertEqual({c.args[-2:] for c in run_case.call_args_list}, {("gpt-6-luna", "xhigh")})

    def test_codex_and_claude_turns_carry_the_override_in_argv(self):
        from harnesses import claude_code, codex
        run = live.Run(Path("/r"), "codex", {"id": "x", "fixture": "relay", "turns": ["go"]}, "0" * 40, 60, model="gpt-6-luna", effort="xhigh")
        flags = codex.config_flags(run)
        self.assertEqual(flags[flags.index('model="gpt-6-luna"') - 1:flags.index('model="gpt-6-luna"') + 3],
                         ["-c", 'model="gpt-6-luna"', "-c", 'model_reasoning_effort="xhigh"'])
        with tempfile.TemporaryDirectory(prefix="pstack-overrides-") as tmp:
            root = Path(tmp).resolve()
            case = {"id": "x", "fixture": "relay", "turns": ["go"], "model": "case-model", "effort": "low"}
            run = live.Run(root, "claude-code", case, "0" * 40, 60, model="claude-sonnet-5-5", effort="high")
            run.project.mkdir(parents=True)
            binary = root / "native.bin"
            binary.write_bytes(b"identity")
            claude_code._bind_paths(run, claude_code.HostRuntime(binary, "test", root / "home", "u", (), (),
                                                                 ((binary, hashlib.sha256(b"identity").hexdigest()),), "/usr/bin:/bin", "/bin/sh"))
            argv = claude_code._command(run, "go", 0).argv
        self.assertEqual(argv[-5:], ("--effort", "high", "--model", "claude-sonnet-5-5", "go"))


def fake_cli(directory, name, script):
    path = Path(directory) / name
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)
    return path


class LoginPreflight(unittest.TestCase):
    """A wave stops on a login the CLI reports gone, before any case spends a token."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-preflight-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def wave(self, harness, *patches):
        stderr = io.StringIO()
        with mock.patch.object(live, "run_case") as run_case, redirect_stderr(stderr):
            for patch in patches:
                self.enterContext(patch)
            code = live.main(["run", "--harness", harness, "--case", "a", "--case", "b", "--out", str(self.tmp / "out")])
        return code, run_case, stderr.getvalue()

    def claude(self, script):
        from harnesses import claude_code
        binary = fake_cli(self.tmp, "claude", script)
        self.enterContext(mock.patch.object(claude_code, "CLAUDE_LAUNCHER", binary))
        runtime = claude_code.HostRuntime(binary, "test", self.tmp, "test-user", (), (),
                                          ((binary, claude_code._digest(binary)),), "/usr/bin:/bin", "/bin/sh")
        return mock.patch.object(claude_code, "_host_runtime", return_value=runtime)

    def codex(self, script, with_auth=True):
        home = self.tmp / "codex-home"
        home.mkdir(exist_ok=True)
        if with_auth:
            (home / "auth.json").write_text("{}")
        binary = fake_cli(self.tmp, "codex", script)
        return mock.patch.dict(os.environ, {"CODEX_HOME": str(home), "CODEX_BIN": str(binary)})

    def grok(self, expires_at, models=":", version="echo grok 1"):
        from harnesses import grok
        home = self.tmp / "grok-home"
        home.mkdir(exist_ok=True)
        (home / "auth.json").write_text(json.dumps({"xai": {"key": "k", "expires_at": expires_at}}))
        script = f'case "$1" in --version) {version};; models) echo models >> "{self.tmp / "models-calls"}"; {models};; esac\n'
        binary = fake_cli(self.tmp, "grok", script)
        self.enterContext(mock.patch.dict(os.environ, {"GROK_BIN": str(binary)}))
        return mock.patch.object(grok, "host_grok_home", return_value=home)

    @staticmethod
    def grok_renews(expires_at):
        return f"echo '{json.dumps({'xai': {'key': 'k', 'expires_at': expires_at}})}' > \"$GROK_HOME/auth.json\""

    def grok_renews_when_due(self, expires_at):
        due = ('import datetime, json, os, sys; '
               'expiry = datetime.datetime.fromisoformat(json.load(open(os.environ["GROK_HOME"] + "/auth.json"))["xai"]["expires_at"]); '
               'left = (expiry - datetime.datetime.now(datetime.timezone.utc)).total_seconds(); '
               'sys.exit(left > int(os.environ.get("GROK_AUTH_EARLY_INVALIDATION_SECS") or 300))')
        return f"if \"{sys.executable}\" -c '{due}'; then {self.grok_renews(expires_at)}; fi"

    @staticmethod
    def in_seconds(seconds):
        return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def assertGrokStopped(self, outcome, *causes):
        self.assertStopped(outcome, "grok", "grok login")
        for cause in causes:
            self.assertIn(cause, outcome[2])

    def assertGrokNotRun(self, outcome, *causes):
        code, run_case, stderr = outcome
        self.assertEqual(code, 3)
        run_case.assert_not_called()
        self.assertEqual(list((self.tmp / "out").iterdir()), [])
        for cause in causes:
            self.assertIn(cause, stderr)
        self.assertIn("grok login is not usable", stderr)
        self.assertNotIn("Run `grok login`", stderr)
        self.assertIn("Get `grok models` to run on the host, then start the wave again", stderr)

    def assertStopped(self, outcome, cli, command):
        code, run_case, stderr = outcome
        self.assertEqual(code, 3)
        run_case.assert_not_called()
        self.assertEqual(list((self.tmp / "out").iterdir()), [])
        self.assertIn(f"{cli} login is not usable", stderr)
        self.assertIn(f"Run `{command}`", stderr)

    def test_claude_code_reporting_no_login_stops_the_wave(self):
        outcome = self.wave("claude-code", self.claude('echo \'{"loggedIn": false}\'; exit 1\n'))
        self.assertStopped(outcome, "claude", "claude auth login")

    def test_claude_code_exiting_zero_with_loggedin_false_still_stops_the_wave(self):
        outcome = self.wave("claude-code", self.claude('echo \'{"loggedIn": false}\'\n'))
        self.assertStopped(outcome, "claude", "claude auth login")

    def test_claude_code_status_does_not_see_credentials_only_the_host_shell_exports(self):
        script = 'if [ -n "$ANTHROPIC_API_KEY" ]; then echo \'{"loggedIn": true}\'; else echo \'{"loggedIn": false}\'; exit 1; fi\n'
        outcome = self.wave("claude-code", self.claude(script), mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "host-only"}))
        self.assertStopped(outcome, "claude", "claude auth login")

    def test_codex_login_status_failing_stops_the_wave(self):
        script = 'case "$1" in --version) echo codex 1;; *) echo "Not logged in" >&2; exit 1;; esac\n'
        self.assertStopped(self.wave("codex", self.codex(script)), "codex", "codex login")

    def test_codex_without_an_auth_file_stops_the_wave_even_when_the_cli_says_logged_in(self):
        script = 'case "$1" in --version) echo codex 1;; *) echo "Logged in using ChatGPT";; esac\n'
        self.assertStopped(self.wave("codex", self.codex(script, with_auth=False)), "codex", "codex login")

    def test_grok_with_an_expired_host_token_stops_the_wave(self):
        self.assertStopped(self.wave("grok", self.grok("2020-01-01T00:00:00Z")), "grok", "grok login")

    def test_grok_renews_an_expired_host_token_and_runs_every_case(self):
        code, run_case, _ = self.wave("grok", self.grok("2020-01-01T00:00:00Z", self.grok_renews("2999-01-01T00:00:00Z")))
        self.assertEqual((code, [c.args[1] for c in run_case.call_args_list]), (0, ["a", "b"]))

    def test_grok_with_a_valid_host_token_runs_every_case_without_renewing(self):
        code, run_case, _ = self.wave("grok", self.grok("2999-01-01T00:00:00Z"))
        self.assertEqual((code, [c.args[1] for c in run_case.call_args_list]), (0, ["a", "b"]))
        self.assertFalse((self.tmp / "models-calls").exists())

    def test_grok_renews_a_host_token_inside_the_margin_even_when_the_host_sets_a_shorter_early_refresh(self):
        code, run_case, _ = self.wave("grok", self.grok(self.in_seconds(240), self.grok_renews_when_due("2999-01-01T00:00:00Z")),
                                      mock.patch.dict(os.environ, {"GROK_AUTH_EARLY_INVALIDATION_SECS": "60"}))
        self.assertEqual((code, [c.args[1] for c in run_case.call_args_list]), (0, ["a", "b"]))

    def test_grok_with_an_expired_host_token_that_renewal_leaves_expired_says_when_it_expired(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z"))
        self.assertGrokStopped(outcome, "the host token expired at 2020-01-01T00:00Z")

    def test_grok_with_a_host_token_inside_the_margin_that_renewal_leaves_alone_says_when_it_expires(self):
        outcome = self.wave("grok", self.grok(self.in_seconds(240)))
        self.assertGrokStopped(outcome, "the host token expires at")

    def test_grok_renewal_that_removes_the_host_login_stops_the_wave_saying_grok_removed_it(self):
        removes = 'rm -f "$GROK_HOME/auth.json"; echo "You are not authenticated."'
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", removes))
        self.assertGrokStopped(outcome, "grok removed the host login", "exited 0", "You are not authenticated.")

    def test_grok_renewal_exiting_zero_without_renewing_stops_the_wave_with_its_stdout(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", 'echo "You are not authenticated."'))
        self.assertGrokStopped(outcome, "exited 0", "You are not authenticated.")

    def test_grok_renewal_output_in_the_refusal_keeps_its_first_100_and_last_200_characters(self):
        output = "HEAD-OF-OUTPUT" + "0" * 400 + "TAIL-OF-OUTPUT"
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", f"printf '{output}'; exit 1"))
        self.assertGrokStopped(outcome, f"exited 1: {output[:100]} ... {output[-200:]}. Run")

    def test_grok_renewal_exiting_zero_keeps_the_cause_line_ahead_of_a_long_model_list(self):
        listing = "".join(f"\\ngrok-model-{n} (a catalog entry)" for n in range(30))
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", f"printf 'You are not authenticated.{listing}'"))
        self.assertGrokStopped(outcome, "exited 0: You are not authenticated. grok-model-0")

    def test_grok_renewal_output_in_the_refusal_puts_stdout_before_stderr_and_trims_the_edges(self):
        script = "printf ' ERR-LINE\\n\\n' >&2; printf '  \\n OUT-LINE \\n'; exit 1"
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", script))
        self.assertGrokStopped(outcome, "exited 1: OUT-LINE ERR-LINE. Run")

    def test_grok_renewal_output_spanning_lines_stays_on_one_refusal_line(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", "printf 'one\\ntwo\\n' >&2; printf 'three\\n'; exit 1"))
        self.assertGrokStopped(outcome, "exited 1: three one two. Run")
        self.assertEqual(len(outcome[2].splitlines()), 1)

    def test_grok_renewal_runs_without_the_debug_logging_the_host_turns_on(self):
        seen = self.tmp / "renewal-env"
        records = f'echo "RUST_LOG=$RUST_LOG GROK_LOG_FILE=${{GROK_LOG_FILE-absent}}" > "{seen}"'
        self.wave("grok", self.grok("2020-01-01T00:00:00Z", records),
                  mock.patch.dict(os.environ, {"RUST_LOG": "trace", "GROK_LOG_FILE": str(self.tmp / "grok.log")}))
        self.assertEqual(seen.read_text(), "RUST_LOG=off GROK_LOG_FILE=absent\n")

    def test_grok_renewal_exiting_nonzero_stops_the_wave_with_its_output(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", 'echo "xai refused the refresh grant" >&2; exit 7'))
        self.assertGrokStopped(outcome, "exited 7", "xai refused the refresh grant")

    def test_grok_renewal_with_undecodable_output_still_stops_the_wave_with_its_exit_code(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", "printf '\\377' >&2; exit 1"))
        self.assertGrokStopped(outcome, "exited 1")

    def test_grok_renewal_that_hangs_stops_the_wave_as_not_finished(self):
        from harnesses import grok
        run = subprocess.run

        def shortened(argv, **kwargs):
            if argv[-1] == "models" and kwargs.get("timeout") is not None:
                kwargs["timeout"] = 0.5
            return run(argv, **kwargs)

        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", "exec sleep 3"),
                            mock.patch.object(grok.subprocess, "run", shortened))
        self.assertGrokNotRun(outcome, "did not finish", "TimeoutExpired")

    def test_grok_with_no_working_binary_stops_the_wave_saying_the_renewal_never_ran(self):
        from harnesses import grok
        empty = self.tmp / "empty-path"
        empty.mkdir()
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", version="exit 1"),
                            mock.patch.dict(os.environ, {"PATH": str(empty)}),
                            mock.patch.object(grok, "DEFAULT_BIN", self.tmp / "no-such-grok"))
        self.assertGrokNotRun(outcome, "no working grok binary", "never ran")

    def test_grok_binary_path_the_host_cannot_search_stops_the_wave_saying_the_renewal_never_ran(self):
        from harnesses import grok
        locked = self.tmp / "locked"
        locked.mkdir()
        (locked / "grok").write_text("")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o700)
        empty = self.tmp / "empty-path"
        empty.mkdir()
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z"),
                            mock.patch.dict(os.environ, {"GROK_BIN": str(locked / "grok"), "PATH": str(empty)}),
                            mock.patch.object(grok, "DEFAULT_BIN", self.tmp / "no-such-grok"))
        self.assertGrokNotRun(outcome, "no working grok binary", "never ran")

    def test_grok_binary_whose_version_output_is_undecodable_still_runs_the_wave(self):
        code, run_case, _ = self.wave("grok", self.grok("2020-01-01T00:00:00Z", self.grok_renews("2999-01-01T00:00:00Z"),
                                                        version="printf 'grok \\377 1'"))
        self.assertEqual((code, [c.args[1] for c in run_case.call_args_list]), (0, ["a", "b"]))

    def test_grok_binary_that_fails_its_version_probe_with_undecodable_output_stops_the_wave_as_never_ran(self):
        from harnesses import grok
        empty = self.tmp / "empty-path"
        empty.mkdir()
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", version="printf '\\377' >&2; exit 1"),
                            mock.patch.dict(os.environ, {"PATH": str(empty)}),
                            mock.patch.object(grok, "DEFAULT_BIN", self.tmp / "no-such-grok"))
        self.assertGrokNotRun(outcome, "no working grok binary", "never ran")

    def test_grok_binary_that_vanishes_before_the_renewal_stops_the_wave_as_not_finished(self):
        outcome = self.wave("grok", self.grok("2020-01-01T00:00:00Z", version='echo grok 1; rm -f "$0"'))
        self.assertGrokNotRun(outcome, "did not finish", "FileNotFoundError")

    def test_grok_preparation_that_never_ran_the_renewal_hands_its_remedy_to_the_wave_stop(self):
        from harnesses import grok
        empty = self.tmp / "empty-path"
        empty.mkdir()
        run = live.Run(self.tmp / "run", "grok", {"id": "x", "fixture": "relay", "turns": ["one"]}, "0" * 40, 60)
        run.root.mkdir()
        self.grok("2020-01-01T00:00:00Z", version="exit 1")
        with mock.patch.dict(os.environ, {"PATH": str(empty)}), mock.patch.object(grok, "DEFAULT_BIN", self.tmp / "no-such-grok"):
            died = live.drive(grok, run, object())
            self.assertIn("never ran", died[1])
            refusal = str(LoginRequired(*died))
        self.assertNotIn("Run `grok login`", refusal)
        self.assertIn(grok.NOT_RUN_REMEDY, refusal)

    def test_a_valid_login_lets_every_case_run(self):
        script = 'case "$1" in --version) echo codex 1;; *) echo "Logged in using ChatGPT";; esac\n'
        code, run_case, _ = self.wave("codex", self.codex(script))
        self.assertEqual((code, [c.args[1] for c in run_case.call_args_list]), (0, ["a", "b"]))

    def test_a_login_that_dies_mid_wave_stops_the_wave_after_its_error_verdict(self):
        from harnesses import codex
        died = LoginRequired(codex.LOGIN, "turn 0 exited 1")
        stderr = io.StringIO()
        with mock.patch.object(live, "preflight"), mock.patch.object(live, "run_case", side_effect=[died]) as run_case, redirect_stderr(stderr):
            code = live.main(["run", "--harness", "codex", "--case", "a", "--case", "b", "--out", str(self.tmp / "out")])
        self.assertEqual((code, run_case.call_count), (3, 1))
        self.assertIn("Run `codex login`", stderr.getvalue())


class AuthDeath(unittest.TestCase):
    """A turn that ended on an auth failure is the harness failing, not the skill under test."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-auth-death-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def record(self, stderr="", stream="", exit_code=1, timed_out=False):
        (self.tmp / "err").write_text(stderr)
        (self.tmp / "out").write_text(stream)
        return {"exit_code": exit_code, "timed_out": timed_out, "stderr": str(self.tmp / "err"), "stream": str(self.tmp / "out")}

    def test_each_cli_expired_login_message_is_an_auth_death(self):
        from harnesses import claude_code, codex, grok
        cases = [(claude_code.LOGIN, {"stream": '{"type":"result","is_error":true,"result":"Invalid API key \u00b7 Please run /login"}\n'}),
                 (claude_code.LOGIN, {"stderr": "Login expired \u00b7 Please run /login"}),
                 (codex.LOGIN, {"stderr": "Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again."}),
                 (grok.LOGIN, {"stderr": "Authentication required. Run `grok login` to re-authenticate."})]
        for login, streams in cases:
            with self.subTest(cli=login.cli, streams=list(streams)):
                self.assertTrue(auth_death(login, self.record(**streams)))

    def test_the_grok_external_auth_failure_a_real_run_ended_on_is_an_auth_death(self):
        from harnesses import grok
        record = {"exit_code": 1, "timed_out": False, "stream": str(FIXTURES / "grok-external-auth.stream.json"),
                  "stderr": str(FIXTURES / "grok-external-auth.stderr.txt")}
        self.assertTrue(auth_death(grok.LOGIN, record))
        self.assertTrue(auth_death(grok.LOGIN, {"exit_code": 1, "timed_out": False, "stream": record["stream"]}))
        self.assertTrue(auth_death(grok.LOGIN, {"exit_code": 1, "timed_out": False, "stderr": record["stderr"]}))

    def test_the_claude_code_401_a_real_run_ended_on_is_an_auth_death(self):
        from harnesses import claude_code
        record = {"exit_code": 1, "timed_out": False, "stream": str(FIXTURES / "claude-code-401-last-line.jsonl")}
        self.assertIn("Failed to authenticate", auth_death(claude_code.LOGIN, record))

    def test_a_turn_that_exited_zero_or_timed_out_or_died_for_another_reason_is_not_an_auth_death(self):
        from harnesses import claude_code
        login = claude_code.LOGIN
        text = "Please run /login"
        for name, record in (("exit zero", self.record(stderr=text, exit_code=0)),
                             ("timed out", self.record(stderr=text, exit_code=-9, timed_out=True)),
                             ("other failure", self.record(stderr="segmentation fault"))):
            with self.subTest(name):
                self.assertIsNone(auth_death(login, record))

    def test_a_login_message_quoted_early_in_a_longer_stream_is_not_an_auth_death(self):
        from harnesses import claude_code
        stream = '{"type":"assistant","text":"the docs say Please run /login"}\n{"type":"result","is_error":true,"result":"max turns"}\n'
        record = self.record(stream=stream)
        self.assertIsNone(auth_death(claude_code.LOGIN, record))

    def test_drive_ends_the_run_at_the_dying_turn_and_names_the_login(self):
        from harnesses import claude_code
        turns = []

        def turn(run, text, index):
            turns.append(index)
            return {"index": index, **self.record(stderr="Not logged in \u00b7 Please run /login")}

        module = mock.Mock(SHARES_HOST_TMP=False, LOGIN=claude_code.LOGIN, turn=turn)
        run = live.Run(self.tmp, "claude-code", {"id": "x", "fixture": "relay", "turns": ["one", "two"]}, "0" * 40, 60)
        with mock.patch.object(live, "_write_record"):
            login, detail, remedy = live.drive(module, run, object())
        self.assertEqual((login.cli, turns, remedy), ("claude", [0], None))
        self.assertIn("turn 0 exited 1", detail)
        self.assertIn("Not logged in", detail)

    def test_drive_reports_a_login_that_died_in_prepare(self):
        from harnesses import grok
        module = mock.Mock(SHARES_HOST_TMP=False, LOGIN=grok.LOGIN, prepare=mock.Mock(side_effect=LoginRequired(grok.LOGIN, "token expired")))
        run = live.Run(self.tmp, "grok", {"id": "x", "fixture": "relay", "turns": ["one"]}, "0" * 40, 60)
        self.assertEqual(live.drive(module, run, object()), (grok.LOGIN, "token expired", None))
        module.turn.assert_not_called()


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class ErrorRun(unittest.TestCase):
    def test_a_run_that_dies_on_auth_is_graded_error_not_fail_and_stops_the_wave(self):
        import report
        from harnesses import codex
        case = live.load_case("principle-steer-run")
        case["turns"] = ["first", "second"]
        case["tmp_lock"] = False
        with tempfile.TemporaryDirectory(prefix="pstack-live-error-") as tmp:
            out = Path(tmp).resolve()

            def turn(run, text, index):
                (run.root / "err").write_text("Please log out and sign in again.")
                (run.root / "out").write_bytes(b"")
                return {"index": index, "session_id": "s", "argv": ["codex", text], "exit_code": 1, "timed_out": False,
                        "duration_s": 0.1, "stream": str(run.root / "out"), "stderr": str(run.root / "err")}

            def prepare(run):
                (run.root / "launch.json").write_text(json.dumps({"path": "synthetic-no-model", "source": "test", "version": "test", "rejected": []}))

            output = io.StringIO()
            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(codex, "prepare", side_effect=prepare), \
                    mock.patch.object(codex, "turn", side_effect=turn) as turns, redirect_stdout(output):
                with self.assertRaisesRegex(live.LoginRequired, "Run `codex login`"):
                    live.run_case("codex", case["id"], "HEAD", out, 0)
            [root] = [p.parent for p in out.rglob("verdict.json")]
            verdict = json.loads((root / "verdict.json").read_text())
            table = report.render(out, upstream=out)
        self.assertEqual(turns.call_count, 1)
        self.assertEqual({r["verdict"] for r in verdict["promises"].values()}, {"ERROR"})
        self.assertEqual(set(verdict["promises"]), set(case["promises"]))
        self.assertEqual(verdict["error"]["relogin"], "codex login")
        self.assertEqual(set(json.loads(output.getvalue())["verdicts"].values()), {"ERROR"})
        self.assertIn("codex pass rate: none graded (ERROR", table)

    def test_a_login_that_dies_after_the_graded_behavior_keeps_the_graders_verdict(self):
        import report
        from harnesses import claude_code
        case = live.load_case("feature-boundary-run")
        case["tmp_lock"] = False
        trace = json.loads((FIXTURES / "claude-code-after-ipc-trace.json").read_text())

        def turn(run, text, index):
            (run.root / "err").write_bytes(b"")
            return {"index": index, "session_id": "s", "argv": ["claude", text], "exit_code": 1, "timed_out": False,
                    "duration_s": 582.6, "stream": str(FIXTURES / "claude-code-401-last-line.jsonl"), "stderr": str(run.root / "err")}

        with tempfile.TemporaryDirectory(prefix="pstack-live-late-death-") as tmp:
            out = Path(tmp).resolve()
            output = io.StringIO()
            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(claude_code, "prepare"), \
                    mock.patch.object(claude_code, "turn", side_effect=turn), \
                    mock.patch.object(claude_code, "harvest", return_value=trace), redirect_stdout(output):
                with self.assertRaisesRegex(live.LoginRequired, "Run `claude auth login`"):
                    live.run_case("claude-code", case["id"], "HEAD", out, 0)
            [root] = [p.parent for p in out.rglob("verdict.json")]
            verdict = json.loads((root / "verdict.json").read_text())
            sealed = json.loads((root / "trace.json").read_text())
            table = report.render(out, upstream=out)
        promise = "poteto-mode-triggers-architect-on-boundary-crossing"
        self.assertEqual(verdict["promises"][promise]["verdict"], "PASS")
        self.assertEqual(verdict["error"]["cli"], "claude")
        self.assertEqual(sealed["harness"], "claude-code")
        self.assertEqual(json.loads(output.getvalue())["verdicts"], {promise: "PASS"})
        self.assertIn("claude-code pass rate: 1 of 1", table)

    def claude_feature_run_that_never_started(self, out):
        from harnesses import claude_code
        case = live.load_case("feature-run")
        case["tmp_lock"] = False
        trace = json.loads((FIXTURES / "claude-code-never-started-trace.json").read_text())

        def turn(run, text, index):
            (run.root / "err").write_bytes(b"")
            return {"index": index, "session_id": "s", "argv": ["claude", text], "exit_code": 1, "timed_out": False,
                    "duration_s": 4.7, "stream": str(FIXTURES / "claude-code-401-last-line.jsonl"), "stderr": str(run.root / "err")}

        output = io.StringIO()
        with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(claude_code, "prepare"), \
                mock.patch.object(claude_code, "turn", side_effect=turn), \
                mock.patch.object(claude_code, "harvest", return_value=trace), redirect_stdout(output):
            with self.assertRaisesRegex(live.LoginRequired, "Run `claude auth login`"):
                live.run_case("claude-code", case["id"], "HEAD", out, 0)
        return json.loads(output.getvalue())["authorization_id"]

    def test_first_publication_already_has_the_sealed_error_when_return_is_interrupted(self):
        import grade_boundary

        class Interrupted(BaseException):
            pass

        with tempfile.TemporaryDirectory(prefix="pstack-first-error-") as tmp:
            out = Path(tmp).resolve()
            writes = []
            write = grade_boundary._Root.write

            def interrupt_after_publication(root, name, data):
                result = write(root, name, data)
                if name == "verdict.json":
                    writes.append(json.loads(data))
                    raise Interrupted()
                return result

            with mock.patch.object(grade_boundary._Root, "write", interrupt_after_publication):
                with self.assertRaises(Interrupted):
                    self.claude_feature_run_that_never_started(out)
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0]["error"]["relogin"], "claude auth login")
            self.assertEqual({r["verdict"] for r in writes[0]["promises"].values() if not r.get("not_applicable")}, {"ERROR"})
            controller = grade_boundary._Controller(out)
            self.addCleanup(controller.root.close)
            [envelope] = [p for p in controller.root.path.glob("*.json") if p.name != "key.json"]
            handle, state = controller.load(envelope.stem)
            self.assertEqual(state["error"], writes[0]["error"])
            self.assertEqual(live.grade(handle), writes[0])

    def test_regrading_a_run_a_dead_login_ended_keeps_its_error_marks(self):
        import report
        with tempfile.TemporaryDirectory(prefix="pstack-live-regrade-") as tmp:
            out = Path(tmp).resolve()
            run_id = self.claude_feature_run_that_never_started(out)
            with redirect_stdout(io.StringIO()):
                code = live.main(["grade", run_id, "--out", str(out)])
            [root] = [p.parent for p in out.rglob("verdict.json")]
            verdict = json.loads((root / "verdict.json").read_text())
            table = report.render(out, upstream=out)
        self.assertEqual(code, 0)
        self.assertEqual(verdict["error"]["relogin"], "claude auth login")
        self.assertEqual({p: r["verdict"] for p, r in verdict["promises"].items() if not r.get("not_applicable")},
                         {p: "ERROR" for p in verdict["promises"] if p != "persona-delivery-hermes-grok"})
        self.assertIn("claude-code pass rate: none graded (ERROR 10 excluded)", table)

    def test_a_harvest_refusal_after_an_auth_death_stops_the_batch_before_any_verdict(self):
        from harnesses import claude_code
        case = live.load_case("feature-run")
        case["tmp_lock"] = False

        def turn(run, text, index):
            (run.root / "err").write_bytes(b"")
            return {"index": index, "session_id": "s", "argv": ["claude", text], "exit_code": 1, "timed_out": False,
                    "duration_s": 4.7, "stream": str(FIXTURES / "claude-code-401-last-line.jsonl"), "stderr": str(run.root / "err")}

        with tempfile.TemporaryDirectory(prefix="pstack-live-harvest-refused-") as tmp:
            out = Path(tmp).resolve()
            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(claude_code, "prepare"), \
                    mock.patch.object(claude_code, "turn", side_effect=turn), \
                    mock.patch.object(claude_code, "harvest", side_effect=GradeRefused("input_changed", "linked transcript")):
                with self.assertRaisesRegex(GradeRefused, "linked transcript"):
                    live.run_case("claude-code", case["id"], "HEAD", out, 0)
            written = sorted(p.name for p in out.rglob("*.json") if p.name in ("trace.json", "verdict.json"))
        self.assertEqual(written, [])

    def test_a_grok_renewal_that_never_ran_in_preparation_stops_the_wave_without_login_advice(self):
        from harnesses import grok
        case = live.load_case("principle-steer-run")
        case["tmp_lock"] = False
        with tempfile.TemporaryDirectory(prefix="pstack-live-remedy-") as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp).resolve()
            home = out / "grok-home"
            home.mkdir()
            (home / "auth.json").write_text(json.dumps({"xai": {"key": "k", "expires_at": "2020-01-01T00:00:00Z"}}))
            with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(grok, "host_grok_home", return_value=home), \
                    mock.patch.dict(os.environ, {"GROK_BIN": str(out / "no-such-grok"), "PATH": str(Path(shutil.which("git")).parent)}), \
                    mock.patch.object(grok, "DEFAULT_BIN", out / "no-such-grok-either"):
                with self.assertRaises(live.LoginRequired) as refused:
                    live.run_case("grok", case["id"], "HEAD", out, 0)
        self.assertIn("never ran", str(refused.exception))
        self.assertNotIn("Run `grok login`", str(refused.exception))
        self.assertIn(grok.NOT_RUN_REMEDY, str(refused.exception))

    def test_regrading_a_run_whose_login_died_before_any_turn_is_refused_and_keeps_its_verdict(self):
        from harnesses import codex
        case = live.load_case("principle-steer-run")
        case["tmp_lock"] = False
        with tempfile.TemporaryDirectory(prefix="pstack-live-regrade-") as tmp:
            out = Path(tmp).resolve()
            output = io.StringIO()
            with mock.patch.object(live, "load_case", return_value=case), redirect_stdout(output), \
                    mock.patch.object(codex, "prepare", side_effect=LoginRequired(codex.LOGIN, "no login at auth.json")):
                with self.assertRaises(live.LoginRequired):
                    live.run_case("codex", case["id"], "HEAD", out, 0)
            [root] = [p.parent for p in out.rglob("verdict.json")]
            before = (root / "verdict.json").read_bytes()
            with redirect_stderr(io.StringIO()) as refusal:
                code = live.main(["grade", json.loads(output.getvalue())["authorization_id"], "--out", str(out)])
            after = (root / "verdict.json").read_bytes()
        self.assertEqual(code, 2)
        self.assertIn("not sealed", refusal.getvalue())
        self.assertEqual(after, before)
        self.assertEqual({r["verdict"] for r in json.loads(after)["promises"].values()}, {"ERROR"})


class ErrorVerdict(unittest.TestCase):
    def test_pass_and_fail_survive_an_auth_death_and_only_the_undecided_become_error(self):
        from harnesses import codex
        gated = "persona-delivery-hermes-grok"
        case = {"id": "x", "promises": ["a", "b", "c", gated]}
        graded = {"a": {"verdict": "PASS", "failures": [], "evidence": ["e"]},
                  "b": {"verdict": "FAIL", "failures": ["f"], "evidence": []},
                  "c": {"verdict": "INCONCLUSIVE", "failures": ["run killed"], "evidence": []},
                  gated: {"verdict": "INCONCLUSIVE", "failures": ["applies to hermes and grok only"], "evidence": [], "not_applicable": True}}
        verdict = error_verdict(case, "codex", "0" * 40, death_record(codex.LOGIN, "turn 0 exited 1"), graded)
        self.assertEqual({p: r["verdict"] for p, r in verdict["promises"].items()},
                         {"a": "PASS", "b": "FAIL", "c": "ERROR", gated: "INCONCLUSIVE"})
        self.assertEqual(verdict["promises"]["a"], graded["a"])
        self.assertTrue(verdict["promises"][gated]["not_applicable"])
        self.assertEqual(verdict["promises"]["c"]["failures"], ["codex login died: turn 0 exited 1"])
        self.assertEqual(verdict["error"]["relogin"], "codex login")

    def test_a_claude_run_that_never_started_keeps_the_hermes_and_grok_promise_out(self):
        import oracles
        import report
        from harnesses import claude_code
        case = live.load_case("feature-run")
        trace = json.loads((FIXTURES / "claude-code-never-started-trace.json").read_text())
        graded = {pid: oracles.check(pid, trace, case, None) for pid in case["promises"]}
        self.assertIn("run never started", graded["persona-delivery-hermes-grok"]["failures"][0])
        verdict = error_verdict(case, "claude-code", "0" * 40, death_record(claude_code.LOGIN, "turn 0 exited 1"), graded)
        gated = {pid for pid, r in verdict["promises"].items() if r.get("not_applicable")}
        self.assertEqual(gated, {"persona-delivery-hermes-grok"})
        self.assertEqual({r["verdict"] for pid, r in verdict["promises"].items() if pid not in gated}, {"ERROR"})
        with tempfile.TemporaryDirectory(prefix="pstack-error-verdict-") as tmp:
            (Path(tmp) / "verdict.json").write_text(json.dumps(verdict))
            table = report.render(Path(tmp), upstream=Path(tmp))
        self.assertIn("claude-code pass rate: none graded (ERROR 10 excluded)", table)
        self.assertNotIn("persona-delivery-hermes-grok", table)

    def test_an_undecided_promise_that_needs_a_judge_keeps_the_flag_and_excerpt_on_its_error(self):
        import oracles
        from harnesses import codex
        case = {"id": "x", "promises": ["a"]}
        graded = {"a": oracles.inconclusive("wording needs a judge", "seq 4", needs_judge=True, excerpt="the reply says pass")}
        verdict = error_verdict(case, "codex", "0" * 40, death_record(codex.LOGIN, "turn 1 exited 1"), graded)
        self.assertEqual(verdict["promises"]["a"], {"verdict": "ERROR", "failures": ["codex login died: turn 1 exited 1"], "evidence": [],
                                                    "needs_judge": True, "excerpt": "the reply says pass"})

    def test_a_dead_codex_run_marks_error_only_the_promises_that_apply_to_codex(self):
        import report
        from harnesses import codex
        case = live.load_case("feature-run")
        verdict = error_verdict(case, "codex", "0" * 40, death_record(codex.LOGIN, "no login at auth.json"))
        gated = {pid for pid, r in verdict["promises"].items() if r.get("not_applicable")}
        self.assertEqual(gated, {"claude-effort-applies-via-effort-agents", "persona-delivery-hermes-grok"})
        self.assertEqual({r["verdict"] for pid, r in verdict["promises"].items() if pid not in gated}, {"ERROR"})
        self.assertEqual(len(case["promises"]) - len(gated), 9)
        with tempfile.TemporaryDirectory(prefix="pstack-error-verdict-") as tmp:
            (Path(tmp) / "verdict.json").write_text(json.dumps(verdict))
            table = report.render(Path(tmp), upstream=Path(tmp))
        self.assertIn("codex pass rate: none graded (ERROR 9 excluded)", table)
        self.assertNotIn("claude-effort-applies-via-effort-agents", table)

    def test_every_promise_of_every_live_case_answers_the_applicability_probe_on_every_harness(self):
        import report
        from harnesses import codex
        for case_id in sorted(p.name for p in live.CASES.iterdir() if (p / "case.json").is_file()):
            case = live.load_case(case_id)
            if case.get("deferred") or case.get("kind", "live") != "live":
                continue
            for harness in report.HARNESSES:
                with self.subTest(case=case_id, harness=harness):
                    verdict = error_verdict(case, harness, "0" * 40, death_record(codex.LOGIN, "probe"))
                    self.assertEqual(set(verdict["promises"]), set(case["promises"]))


class MakeProject(unittest.TestCase):
    def build(self, commit, branch=None, extra_steps=()):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        (tmp / "fixtures" / "app").mkdir(parents=True)
        (tmp / "fixtures" / "app" / "a.py").write_text('x = "1"\n')
        step = tmp / "histories" / "h" / "step-1"
        step.mkdir(parents=True)
        (step / "a.py").write_text("x = '1'\n")
        for path in (tmp / "fixtures" / "app" / "a.py", step / "a.py"):
            os.utime(path, (1_700_000_000, 1_700_000_000))
        steps = [{"dir": "step-1", "message": "quote style", "commit": commit, **({"branch": branch} if branch else {})}]
        for n, extra in enumerate(extra_steps, start=2):
            (tmp / "histories" / "h" / f"step-{n}").mkdir()
            (tmp / "histories" / "h" / f"step-{n}" / f"f{n}.py").write_text(f"y = {n}\n")
            steps.append({"dir": f"step-{n}", "message": f"step {n}", **extra})
        (tmp / "histories" / "h" / "steps.json").write_text(json.dumps({"fixture": "app", "steps": steps}))
        old = (live.FIXTURES, live.HISTORIES)
        live.FIXTURES, live.HISTORIES = tmp / "fixtures", tmp / "histories"
        self.addCleanup(lambda: setattr(live, "FIXTURES", old[0]) or setattr(live, "HISTORIES", old[1]))
        project = tmp / "work" / "app"
        live.make_project({"fixture": "app", "history": "h"}, project)
        git = lambda *a: subprocess.run(["git", "-C", str(project), *a], capture_output=True, text=True).stdout
        return git

    def test_a_same_size_edit_in_a_history_step_is_committed(self):
        git = self.build(True)
        self.assertEqual(git("log", "--format=%s"), "quote style\ninitial import\n")
        self.assertEqual(git("show", "HEAD:a.py"), "x = '1'\n")

    def test_an_uncommitted_step_stays_in_the_working_tree(self):
        git = self.build(False)
        self.assertEqual(git("log", "--format=%s"), "initial import\n")
        self.assertEqual(git("status", "--short"), " M a.py\n")

    def test_a_step_with_a_branch_commits_there_and_leaves_main_alone(self):
        git = self.build(True, branch="team-filter")
        self.assertEqual(git("branch", "--show-current"), "team-filter\n")
        self.assertEqual(git("log", "--format=%s", "main"), "initial import\n")
        self.assertEqual(git("diff", "--name-only", "main...HEAD"), "a.py\n")

    def test_a_later_step_on_an_existing_branch_keeps_its_commits(self):
        git = self.build(True, branch="feature", extra_steps=[{"branch": "main"}])
        self.assertEqual(git("log", "--format=%s", "main"), "step 2\ninitial import\n")
        self.assertEqual(git("log", "--format=%s", "feature"), "quote style\ninitial import\n")

    def test_the_baseline_holds_every_branchs_commits_and_ends_at_head(self):
        git = self.build(True, branch="feature", extra_steps=[{"branch": "main"}])
        project = Path(git("rev-parse", "--show-toplevel").strip())
        base = live.baseline(project)
        self.assertEqual(sorted(base), sorted(git("rev-list", "--branches").split()))
        self.assertEqual(base[-1], git("rev-parse", "HEAD").strip())
        self.assertEqual(base[0], git("rev-list", "--max-parents=0", "HEAD").strip())


@unittest.skipUnless((platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64"),
                     "canonical grading requires the reviewed Darwin runtime")
class HermesRetention(unittest.TestCase):
    def test_actual_cli_keeps_private_custody_and_exports_final_grades(self):
        from test_hermes_evidence import _OwnerFixture
        from harnesses import hermes
        from test_hermes import HermesDatabase
        fixture = _OwnerFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        out = fixture.base / "cli-runs"
        retained = fixture.base / "retained"
        case = live.load_case("principle-steer-run")
        case["turns"] = ["go"]
        case["entry"] = None
        original_turn = hermes.turn
        owners = []
        def turn(run, text, index):
            record = original_turn(run, text, index)
            owners.append(run._hermes_evidence)
            db = HermesDatabase(hermes.profile(run) / "state.db")
            db.session("root")
            db.con.execute("update sessions set cwd=?", (str(run.project),))
            db.message("root", "user", "go")
            db.message("root", "assistant", "owned CLI reply")
            db.done()
            link = hermes.profile(run) / "lsp/bin/pyright-langserver"
            link.parent.mkdir(parents=True)
            os.symlink(b"../lib/node_modules/pyright/langserver.js", os.fsencode(link))
            return record
        output = io.StringIO()
        with mock.patch.object(live, "load_case", return_value=case), mock.patch.object(hermes, "turn", turn), redirect_stdout(output):
            result = live.main(["run", "--harness", "hermes", "--case", case["id"], "--out", str(out), "--hermes-retain-out", str(retained)])
        self.assertEqual(result, 0)
        screen = json.loads(output.getvalue())
        pair = Path(screen["hermes_pair"])
        root = Path(screen["run"])
        self.assertEqual(json.loads((pair / "run/trace.json").read_text())["final_reply"], "owned CLI reply")
        self.assertEqual((pair / "run/verdict.json").read_bytes(), (root / "verdict.json").read_bytes())
        manifest = json.loads((pair / "pair.json").read_text())
        self.assertEqual(manifest["absent_run_records"], [])
        link_member = "run/hroot/profiles/probe/lsp/bin/pyright-langserver"
        target = b"../lib/node_modules/pyright/langserver.js"
        self.assertEqual(os.readlink(os.fsencode(pair / link_member)), target)
        self.assertEqual(manifest["symlinks"], {link_member: {"target_hex": target.hex()}})
        self.assertTrue(any(k.startswith("hermes-evidence/captures/") for k in manifest["members"]))
        self.assertEqual(owners[0].private_root.parent, retained)
        self.assertEqual(owners[0]._dirs, [])

    def test_cli_retains_preparation_exception_without_success_output(self):
        from test_hermes_evidence import _OwnerFixture
        from harnesses import hermes
        fixture = _OwnerFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original_prepare = hermes.prepare
        error = RuntimeError("owned preparation exception")
        def prepare(run):
            original_prepare(run)
            raise error
        output = io.StringIO()
        retained = fixture.base / "retained-failure"
        with mock.patch.object(hermes, "prepare", prepare), redirect_stdout(output):
            with self.assertRaises(RuntimeError) as raised:
                live.main(["run", "--harness", "hermes", "--case", "principle-steer-run", "--out", str(fixture.base / "failures"),
                           "--hermes-retain-out", str(retained)])
        self.assertIs(raised.exception, error)
        self.assertEqual(output.getvalue(), "")
        pairs = list(retained.glob("pair-*"))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(json.loads((pairs[0] / "pair.json").read_text())["absent_run_records"], ["run.json", "trace.json", "verdict.json"])
        self.assertIn("Hermes exception evidence retained", " ".join(error.__notes__))

    def test_other_adapters_reject_the_hermes_retention_flag(self):
        with self.assertRaisesRegex(ValueError, "requires --harness hermes"):
            live.run_case("codex", "principle-steer-run", "HEAD", Path("/unused"), 0, Path("/unused-retention"))

    def test_export_failure_cannot_print_a_successful_screen_record(self):
        from test_hermes_evidence import _OwnerFixture
        from harnesses import hermes
        from harnesses.hermes_evidence import RetentionUnavailable
        fixture = _OwnerFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        prepare = hermes.prepare
        retained = fixture.base / "retained-collision"
        owners = []
        def collide(run):
            prepare(run)
            owner = run._hermes_evidence
            owners.append(owner)
            (retained / ("pair-" + owner.binding.run_id)).mkdir()
        case = live.load_case("principle-steer-run")
        case["turns"] = ["go"]
        case["entry"] = None
        output = io.StringIO()
        with mock.patch.object(hermes, "prepare", collide), mock.patch.object(live, "load_case", return_value=case), redirect_stdout(output):
            with self.assertRaisesRegex(RetentionUnavailable, "private evidence remains"):
                live.main(["run", "--harness", "hermes", "--case", case["id"], "--out", str(fixture.base / "collision-runs"),
                           "--hermes-retain-out", str(retained)])
        self.assertEqual(output.getvalue(), "")
        self.assertTrue((owners[0].private_root / "meta.json").is_file())
        self.assertEqual(owners[0]._dirs, [])


if __name__ == "__main__":
    unittest.main()
