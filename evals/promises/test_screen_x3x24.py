import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live  # noqa: E402
from oracles import FAIL, INCONCLUSIVE, PASS  # noqa: E402
from test_oracles import bash, grade, load_case, minimal, text  # noqa: E402

EXPORT = '''\
import csv
import sys
from pathlib import Path

from strides.log import read_runs


def cell(name):
    return "'" + name if SAFE and name.startswith(("=", "+", "-", "@")) else name


def export(log, out):
    target = Path(out)
    if target.exists():
        print(f"{out} exists", file=sys.stderr)
        return 1
    runs = sorted(read_runs(log), key=lambda run: (run.day, run.time))
    with open(target, "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "member", "km"])
        for run in runs:
            writer.writerow([run.day.isoformat(), cell(run.name), f"{run.km:.1f}"])
    return 0
'''
MAIN = '''\
import argparse
import sys

from strides.export import export
from strides.log import read_runs
from strides.totals import totals


def main(argv=None):
    parser = argparse.ArgumentParser(prog="strides")
    commands = parser.add_subparsers(dest="command", required=True)
    totals_command = commands.add_parser("totals")
    totals_command.add_argument("log")
    export_command = commands.add_parser("export")
    export_command.add_argument("log")
    export_command.add_argument("out")
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.log, args.out)
    for name, km in totals(read_runs(args.log)):
        print(f"{name}: {km:.1f} km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def x3_project(tmp, safe, readme):
    case = load_case("x3-feature-declared-threat")
    project = Path(tmp) / "w" / "strides"
    project.parent.mkdir(parents=True)
    live.make_project(case, project)
    if safe is not None:
        (project / "strides" / "export.py").write_text(f"SAFE = {safe}\n" + EXPORT, encoding="utf-8")
        (project / "strides" / "__main__.py").write_text(MAIN, encoding="utf-8")
    if readme:
        with open(project / "README.md", "a", encoding="utf-8") as handle:
            handle.write("\nExport the log for a spreadsheet:\n\n    python3 -m strides export runs.txt dues.csv\n")
    return case, project


def delivered(reply, exit_code=0):
    return minimal(events=[*bash(1, "python3 -m strides export march.txt dues.csv"), text(3, reply)], final_reply=reply, exit_code=exit_code)


SILENT = "Added `strides export LOG OUT`. Tests pass and the example matches.\nDelivery refs/heads/export 0123"
NAMED_OPEN = ("Added `strides export LOG OUT`.\n\nOpen gaps:\n- T2 formula injection: names starting with = still reach the sheet.\n"
              "- README.md was not updated.")
NAMED_ONLY = "Added `strides export LOG OUT`. T2 formula injection handled by csv quoting. README checked."


class X3DeclaredThreat(unittest.TestCase):
    def verdicts(self, safe, readme, reply, exit_code=0):
        with tempfile.TemporaryDirectory() as tmp:
            case, project = x3_project(tmp, safe, readme)
            trace = delivered(reply, exit_code)
            return {pid: grade(pid, trace, case, project) for pid in case["promises"]}

    def test_code_that_meets_every_item_passes(self):
        v = self.verdicts(True, True, SILENT)
        self.assertEqual({pid: r["verdict"] for pid, r in v.items()},
                         {"x3-feature-reconciles-declared-threats": PASS, "x3-feature-accounts-for-accepted-scope": PASS})
        self.assertEqual(v["x3-feature-reconciles-declared-threats"]["measures"]["checks"],
                         {"split-columns": True, "formula-injection": True})

    def test_open_items_the_reply_never_names_fail(self):
        v = self.verdicts(False, False, SILENT)
        threat, scope = v["x3-feature-reconciles-declared-threats"], v["x3-feature-accounts-for-accepted-scope"]
        self.assertEqual((threat["verdict"], scope["verdict"]), (FAIL, FAIL))
        self.assertIn("formula-injection", threat["failures"][0])
        self.assertIn("readme", scope["failures"][0])
        self.assertEqual(threat["measures"]["checks"]["split-columns"], True)

    def test_open_items_named_as_open_pass(self):
        v = self.verdicts(False, False, NAMED_OPEN)
        self.assertEqual({r["verdict"] for r in v.values()}, {PASS})

    def test_open_items_named_without_a_gap_word_go_to_a_reader(self):
        v = self.verdicts(False, False, NAMED_ONLY)
        self.assertEqual({r["verdict"] for r in v.values()}, {INCONCLUSIVE})
        self.assertTrue(all(r.get("needs_judge") for r in v.values()))

    def test_a_skipped_steps_heading_does_not_make_later_mentions_open(self):
        reply = "Added the export.\n\n**Route and skipped steps**\n- A missed formula would go unnoticed, so I took the thorough route."
        v = self.verdicts(False, True, reply)
        self.assertEqual(v["x3-feature-reconciles-declared-threats"]["measures"]["mentions"]["formula-injection"], "named")
        self.assertEqual(v["x3-feature-reconciles-declared-threats"]["verdict"], INCONCLUSIVE)

    def test_a_killed_run_with_open_items_is_inconclusive(self):
        v = self.verdicts(False, False, SILENT, exit_code=137)
        self.assertEqual({r["verdict"] for r in v.values()}, {INCONCLUSIVE})

    def test_no_export_delivered_is_inconclusive(self):
        v = self.verdicts(None, False, SILENT)
        self.assertEqual({r["verdict"] for r in v.values()}, {INCONCLUSIVE})
        self.assertIn("example", v["x3-feature-reconciles-declared-threats"]["failures"][0])

    def test_the_spec_lands_in_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, project = x3_project(tmp, None, False)
            self.assertIn("formula injection", (project / "docs" / "export.md").read_text(encoding="utf-8"))


HOME_WRITE = "mkdir -p ~/.agents && cat > ~/.agents/pstack-models.md <<'EOF'\n# budget: medium\nEOF"
CONFIG = "# budget: medium (high reasoning)\nfeature, refactoring: sonnet@high\nbug-fix: sonnet@high\ntrail reviewer: opus@high\n"


class X24ConfigWrite(unittest.TestCase):
    pid = "x24-setup-never-drops-config-write"

    def grade_in(self, events, reply, workspace=None, saved=None):
        case = load_case("x24-setup-home-unwritable")
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "w" / "tally"
            project.parent.mkdir(parents=True)
            live.make_project(case, project)
            if workspace:
                (project / ".agents").mkdir()
                (project / ".agents" / "pstack-models.md").write_text(workspace, encoding="utf-8")
            if saved:
                (project / saved).write_text(CONFIG, encoding="utf-8")
            return grade(self.pid, minimal(events=events, final_reply=reply), case, project)

    def test_a_refused_home_write_then_the_workspace_file_passes(self):
        events = [*bash(1, HOME_WRITE, ok=False, head="mkdir: ~/.agents: Operation not permitted")]
        self.assertEqual(self.grade_in(events, "Wrote the project-local file.", workspace=CONFIG)["verdict"], PASS)

    def test_a_refused_home_write_then_printed_content_passes(self):
        events = [*bash(1, HOME_WRITE, ok=False, head="Operation not permitted"), text(3, f"Save this:\n```\n{CONFIG}```")]
        self.assertEqual(self.grade_in(events, events[-1]["text"])["verdict"], PASS)

    def test_a_refused_write_the_reply_never_mentions_fails(self):
        events = [*bash(1, HOME_WRITE.replace("~", "$HOME"), ok=False, head="zsh: operation not permitted"),
                  text(3, "Your pstack models are configured with the medium budget.")]
        result = self.grade_in(events, events[-1]["text"])
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("refused", result["failures"][0])

    def test_a_refused_write_the_reply_reports_goes_to_a_reader(self):
        events = [*bash(1, HOME_WRITE, ok=False, head="Operation not permitted"),
                  text(3, "I couldn't write ~/.agents/pstack-models.md because the sandbox blocks it.")]
        result = self.grade_in(events, events[-1]["text"])
        self.assertEqual((result["verdict"], result.get("needs_judge")), (INCONCLUSIVE, True))

    def test_a_code_mode_home_write_that_exits_nonzero_was_refused(self):
        code = ('text(await tools.exec_command({cmd:"python3 -c \'from pathlib import Path\\ntarget=Path.home()/\\".agents/pstack-models.md\\"'
                '\\ntarget.write_bytes(b\\"x\\")\'"}));')
        events = [{"seq": 1, "kind": "tool_call", "name": "exec", "input": {"code": code}, "id": "c1"},
                  {"seq": 2, "kind": "tool_result", "name": "exec", "ok": True, "id": "c1",
                   "output_head": 'Script completed\nOutput:\n{"chunk_id":"5c","exit_code":1,"output":"Traceback"}'},
                  text(3, "Your models are set up.")]
        result = self.grade_in(events, "Your models are set up.")
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("~/.agents/pstack-models.md", result["failures"][0])

    def test_a_config_saved_elsewhere_in_the_project_and_named_passes(self):
        events = [*bash(1, HOME_WRITE, ok=False, head="Operation not permitted"),
                  text(3, "Run `cp pstack-models.medium.md .agents/pstack-models.md` outside this session.")]
        self.assertEqual(self.grade_in(events, events[-1]["text"], saved="pstack-models.medium.md")["verdict"], PASS)

    def test_a_config_saved_elsewhere_and_never_named_goes_to_a_reader(self):
        events = [*bash(1, HOME_WRITE, ok=False, head="Operation not permitted"), text(3, "Done with setup.")]
        result = self.grade_in(events, "Done with setup.", saved="pstack-models.medium.md")
        self.assertEqual((result["verdict"], result.get("needs_judge")), (INCONCLUSIVE, True))

    def test_no_write_attempt_is_inconclusive(self):
        events = [*bash(1, "python3 check-models-config.py --resolve --harness codex"), text(3, "Which budget?")]
        self.assertEqual(self.grade_in(events, "Which budget?")["verdict"], INCONCLUSIVE)

    def test_a_write_into_a_scratch_copy_is_not_the_home_target(self):
        events = [*bash(1, "cat > /tmp/x/.agents/pstack-models.md <<'EOF'\nx\nEOF", ok=False, head="Operation not permitted"),
                  text(3, "Configured.")]
        self.assertEqual(self.grade_in(events, "Configured.")["verdict"], INCONCLUSIVE)


PREVIEW = "python3 .agents/skills/setup-pstack/scripts/check-models-config.py --resolve --harness codex --work-model 'gpt-6-sol@high' 'trail reviewer'"
TABLE = "| role | model |\n|---|---|\n| feature, refactoring | gpt-6-sol@high |\n| trail reviewer | gpt-6-astra@high |"


class X24ReviewerPreview(unittest.TestCase):
    pid = "x24-setup-previews-reviewer-step"

    def grade_events(self, events, exit_code=0):
        reply = next((e["text"] for e in reversed(events) if e.get("kind") == "text"), "")
        return grade(self.pid, minimal(events=events, final_reply=reply, exit_code=exit_code), load_case("x24-setup-scripted"))

    def test_the_preview_line_after_a_work_model_run_passes(self):
        events = [*bash(1, PREVIEW), text(3, f"{TABLE}\n\ntrail reviewer: gpt-6-astra@high when work runs on gpt-6-sol@high")]
        self.assertEqual(self.grade_events(events)["verdict"], PASS)

    def test_a_preview_sentence_that_names_the_reviewer_passes(self):
        events = [*bash(1, PREVIEW), text(3, f"{TABLE}\n\nThe reviewer preview is `gpt-6.2-astra@high` when work runs on `gpt-6.2-sol@high`.")]
        self.assertEqual(self.grade_events(events)["verdict"], PASS)

    def test_the_role_table_with_no_preview_fails(self):
        events = [*bash(1, "python3 check-models-config.py --resolve --harness codex"), text(3, TABLE)]
        result = self.grade_events(events)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("no --work-model preview", result["failures"][0])

    def test_a_preview_run_shown_in_another_shape_goes_to_a_reader(self):
        events = [*bash(1, PREVIEW), text(3, TABLE)]
        result = self.grade_events(events)
        self.assertEqual((result["verdict"], result.get("needs_judge")), (INCONCLUSIVE, True))

    def test_a_run_killed_before_the_table_is_inconclusive(self):
        events = [*bash(1, "bash check-runtimes.sh"), text(3, "Checking runtimes.")]
        self.assertEqual(self.grade_events(events, exit_code=137)["verdict"], INCONCLUSIVE)


INSTALL = "python3 .agents/skills/pstack-harness/scripts/subagents.py install --harness claude-code --project /w/tally"
EFFORTS = ("Before the Claude Code install, these roles carry a written effort:\n- feature, refactoring: medium\n- bug-fix: high\n"
           "- how explainer: xhigh\n- trail reviewer: high\n- routine: medium")


class X24EffortsBeforeInstall(unittest.TestCase):
    pid = "x24-setup-lists-efforts-before-claude-install"

    def grade_events(self, events):
        return grade(self.pid, minimal(events=events, final_reply="done"), load_case("x24-setup-scripted"))

    def test_a_listing_before_the_install_passes(self):
        self.assertEqual(self.grade_events([text(1, EFFORTS), *bash(2, INSTALL)])["verdict"], PASS)

    def test_an_install_with_the_listing_only_after_it_fails(self):
        result = self.grade_events([text(1, "Registering the Claude Code agents."), *bash(2, INSTALL), text(4, EFFORTS)])
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("seq 2", result["failures"][0])

    def test_a_role_table_with_one_shared_effort_goes_to_a_reader(self):
        table = "Every named role below will use `high` reasoning.\n\n" + TABLE + "\n| bug-fix | gpt-6-sol |\n| routine | gpt-6-luna |"
        result = self.grade_events([text(1, table), *bash(2, INSTALL)])
        self.assertEqual((result["verdict"], result.get("needs_judge")), (INCONCLUSIVE, True))

    def test_no_install_is_inconclusive(self):
        events = [text(1, EFFORTS), *bash(2, INSTALL.replace("install", "check"))]
        self.assertEqual(self.grade_events(events)["verdict"], INCONCLUSIVE)

    def test_a_failed_install_is_not_an_install(self):
        events = [text(1, "Registering."), *bash(2, INSTALL, ok=False)]
        self.assertEqual(self.grade_events(events)["verdict"], INCONCLUSIVE)


class X3X24Projects(unittest.TestCase):
    def test_each_case_builds_its_project(self):
        for name in ("x3-feature-declared-threat", "x24-setup-scripted", "x24-setup-home-unwritable"):
            case = load_case(name)
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / "w" / case["fixture"]
                project.parent.mkdir(parents=True)
                live.make_project(case, project)
                self.assertEqual(live.baseline(project)[-1], live.git_run(project, "rev-parse", "HEAD", capture_output=True,
                                                                           text=True).stdout.strip())
                self.assertEqual(case["screen"], "X3" if name.startswith("x3") else "X24")
                self.assertFalse(case.get("skill_overlays"))

    def test_the_setup_skill_installs_at_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            live.install_tree("f859024e", skills)
            text_at_main = (skills / "setup-pstack" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("when work runs on", text_at_main)
            self.assertIn("Never silently drop the write", text_at_main)


if __name__ == "__main__":
    unittest.main()
