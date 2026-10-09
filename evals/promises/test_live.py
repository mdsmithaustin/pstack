import fcntl
import hashlib
import json
import io
import os
import platform
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout
from contextlib import nullcontext

import live
from grade_boundary import GradeRefused, _authorize_fixture

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
                        root = live.run_case(harness, case["id"], "HEAD", out, 0)
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
        case = live.load_case("deslop-handoff-use")
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
                root = live.run_case("codex", case["id"], "HEAD", out, 0, model="gpt-6-luna", effort="xhigh")
            installed = (root / "w" / "rollup" / ".agents/skills/deslop/SKILL.md").read_text()
            trace = json.loads((root / "trace.json").read_text())
            record = json.loads((root / "run.json").read_text())
            verdict = json.loads((root / "verdict.json").read_text())
        self.assertEqual(installed.count("A comment the rules below do not settle needs a second review. Use the **no-comments** skill."), 1)
        self.assertNotIn("go to `/no-comments`.", installed)
        self.assertIn("no-comments", trace["x_implicit_off"])
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

    def test_every_handoff_arm_rewrites_the_current_step_5_sentence(self):
        expected = {"deslop-handoff-slash": DESLOP_STEP_5,
                    "deslop-handoff-bold": "Comments the rules below do not settle go to the **no-comments** skill.",
                    "deslop-handoff-use": "A comment the rules below do not settle needs a second review. Use the **no-comments** skill."}
        for case_id, sentence in expected.items():
            with self.subTest(case=case_id):
                skills = self.tree((live.ROOT / "skills" / "deslop" / "SKILL.md").read_text())
                live.apply_overlays(live.load_case(case_id), skills)
                text = (skills / "deslop" / "SKILL.md").read_text()
                self.assertEqual(text.count(sentence), 1)
                self.assertEqual(text.count(DESLOP_STEP_5), int(case_id == "deslop-handoff-slash"))


class NameOnlySet(unittest.TestCase):
    def test_the_set_holds_skills_whose_policy_turns_implicit_invocation_off(self):
        with tempfile.TemporaryDirectory(prefix="pstack-implicit-") as tmp:
            skills = Path(tmp)
            for name, yaml in (("gated", "policy:\n  allow_implicit_invocation: false\n"), ("open", "policy:\n  allow_implicit_invocation: true\n"),
                               ("other", "interface:\n  allow_implicit_invocation: false\n"), ("bare", None)):
                (skills / name / "agents").mkdir(parents=True)
                (skills / name / "SKILL.md").write_text(f"# {name}\n")
                if yaml is not None:
                    (skills / name / "agents" / "openai.yaml").write_text(yaml)
            (skills / "stray" / "agents").mkdir(parents=True)
            (skills / "stray" / "agents" / "openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n")
            self.assertEqual(live.implicit_off(skills), ["gated"])


class RunOverrides(unittest.TestCase):
    def test_model_and_effort_refuse_harnesses_without_an_override(self):
        for harness in ("hermes", "grok"):
            with self.subTest(harness=harness), self.assertRaisesRegex(ValueError, "--model and --effort support claude-code, codex, not " + harness):
                live.run_case(harness, "principle-steer-run", "HEAD", Path("/unused"), 0, model="m")

    def test_the_cli_passes_model_and_effort_to_every_case(self):
        with tempfile.TemporaryDirectory(prefix="pstack-overrides-") as tmp, mock.patch.object(live, "run_case") as run_case:
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
