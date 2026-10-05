import json
import io
import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout
from contextlib import nullcontext

import live
from grade_boundary import _authorize_fixture

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
