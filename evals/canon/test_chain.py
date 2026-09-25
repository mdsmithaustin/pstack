import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("canon_chain", ROOT / "chain.py")
chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chain)

FIXTURES = ROOT / "fixtures" / "chain"
FEATURE = "1. `how` over the affected subsystem.\n2. `architect` for parallel design exploration.\n3. Write the throughput checkpoint.\n4. Delegate code-writing to a subagent.\n"
TREE = {path: 10 for path in (
    "poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md", "poteto-mode/playbooks/refactoring.md",
    "unslop/SKILL.md", "how/SKILL.md", "architect/SKILL.md", "pstack-harness/SKILL.md",
    "pstack-harness/references/named-roles.md", "principle-model-the-domain/SKILL.md",
    "principle-prove-it-works/SKILL.md", "principle-sequence-verifiable-units/SKILL.md",
    "principle-laziness-protocol/SKILL.md", "principle-test-behavior-not-implementation/SKILL.md",
)}
PRINCIPLES = {
    "principle-laziness-protocol": "Laziness Protocol",
    "principle-model-the-domain": "Model the Domain",
    "principle-prove-it-works": "Prove It Works",
    "principle-test-behavior-not-implementation": "Test Behavior, Not Implementation",
}


def run_stages(trace, owner="poteto-mode/playbooks/feature.md", injected=True, workspace=True):
    return chain.stages(trace, case="session-tree", owner=owner, injected=injected,
                        playbook_texts={"feature": FEATURE}, principles=PRINCIPLES, workspace=workspace)


class ClaudeTraceTests(unittest.TestCase):
    """A trimmed Claude -p stream-json run of the session-tree case: the lead
    reads the Feature playbook and two leaves, spawns one delegate, and the
    delegate edits the checkout after one of its commands is denied."""

    def setUp(self):
        self.trace = chain.parse_claude((FIXTURES / "claude-trace.jsonl").read_text().splitlines(), TREE)
        self.stages = run_stages(self.trace)

    def test_lead_reads_one_playbook_the_expected_one(self):
        self.assertEqual((self.stages["playbook_read"], self.stages["playbook_matched"]), (["feature"], True))

    def test_leaf_reads_carry_their_event_index_and_reader(self):
        self.assertEqual(self.stages["leaf_reads"], [
            {"path": "principle-model-the-domain/SKILL.md", "index": 6, "actor": "main", "partial": False},
            {"path": "principle-laziness-protocol/SKILL.md", "index": 7, "actor": "main", "partial": False},
        ])

    def test_owner_playbook_is_read_before_the_delegate_first_edits(self):
        self.assertEqual((self.stages["first_edit"], self.stages["leaf_before_first_edit"]), (13, True))

    def test_one_spawn_whose_brief_names_the_data_shape(self):
        self.assertEqual(self.stages["delegation"], {
            "spawns": 1, "waits": 0, "delegated": True, "brief_names_shape": True, "delegate_reads": [],
        })

    def test_permission_denials_are_counted(self):
        self.assertEqual(self.stages["tools_denied"], 2)

    def test_reply_cites_two_principles_whose_leaves_the_lead_never_read(self):
        self.assertEqual(self.stages["citations"], {
            "cited": ["principle-prove-it-works", "principle-test-behavior-not-implementation"],
            "unread": ["principle-prove-it-works", "principle-test-behavior-not-implementation"],
            "only_read": False,
        })

    def test_the_run_has_no_worklist_tool_to_call(self):
        self.assertEqual(self.stages["worklist"], {
            "tool_offered": False, "tool_called": False, "text_list": False, "verbatim_fraction": 0.0, "echoed_fraction": 0.0,
        })

    def test_the_slash_command_is_listed(self):
        self.assertIn("poteto-mode", self.trace.slash_commands)


class CodexTraceTests(unittest.TestCase):
    """A trimmed Codex exec --json run of the same case: shell reads, a worklist
    written into a message, a wait on a delegate it never shows spawning, and
    one apply_patch file change."""

    def setUp(self):
        self.trace = chain.parse_codex((FIXTURES / "codex-trace.jsonl").read_text().splitlines(), TREE)
        self.stages = run_stages(self.trace)

    def test_cat_of_several_files_reads_each_in_full(self):
        self.assertEqual([(read["path"], read["index"]) for read in self.stages["leaf_reads"]], [
            ("unslop/SKILL.md", 2), ("pstack-harness/SKILL.md", 2), ("how/SKILL.md", 4), ("architect/SKILL.md", 4),
            ("principle-model-the-domain/SKILL.md", 4), ("principle-prove-it-works/SKILL.md", 4),
            ("principle-sequence-verifiable-units/SKILL.md", 4), ("principle-laziness-protocol/SKILL.md", 4),
            ("pstack-harness/references/named-roles.md", 4),
        ])

    def test_worklist_in_a_message_that_does_not_copy_the_steps(self):
        self.assertEqual(self.stages["worklist"], {
            "tool_offered": None, "tool_called": False, "text_list": True, "verbatim_fraction": 0.0, "echoed_fraction": 0.0,
        })

    def test_a_wait_marks_delegation_without_a_visible_spawn(self):
        self.assertEqual(self.stages["delegation"], {
            "spawns": 0, "waits": 1, "delegated": True, "brief_names_shape": None, "delegate_reads": [],
        })

    def test_file_change_is_the_first_edit_after_the_playbook_read(self):
        self.assertEqual((self.stages["first_edit"], self.stages["leaf_before_first_edit"]), (7, True))

    def test_reply_cites_only_leaves_it_read(self):
        self.assertEqual(self.stages["citations"], {
            "cited": ["principle-laziness-protocol", "principle-model-the-domain"], "unread": [], "only_read": True,
        })


class ShellEffectsTests(unittest.TestCase):
    def test_greater_than_inside_a_quoted_script_is_not_a_write(self):
        self.assertEqual(chain.shell_effects("""python3 -c "print(len(x) > 3)" """, TREE), ([], []))

    def test_redirect_outside_quotes_is_a_write(self):
        self.assertEqual(chain.shell_effects("echo hi > notes.txt", TREE), ([], ["notes.txt"]))

    def test_for_loop_reads_every_word(self):
        reads, _ = chain.shell_effects(
            "/bin/zsh -lc 'for n in how architect; do cat skills/pstack/$n/SKILL.md; done'", TREE)

        self.assertEqual(reads, [("how/SKILL.md", False), ("architect/SKILL.md", False)])

    def test_cd_then_relative_path_resolves(self):
        reads, _ = chain.shell_effects("cd .claude/skills/poteto-mode && cat playbooks/refactoring.md", TREE)

        self.assertEqual(reads, [("poteto-mode/playbooks/refactoring.md", False)])

    def test_head_pipe_and_short_sed_range_are_partial(self):
        reads, _ = chain.shell_effects("cat how/SKILL.md | head -3; sed -n '1,4p' architect/SKILL.md; sed -n '1,40p' unslop/SKILL.md", TREE)

        self.assertEqual(reads, [("how/SKILL.md", True), ("architect/SKILL.md", True), ("unslop/SKILL.md", False)])

    def test_search_commands_read_nothing(self):
        self.assertEqual(chain.shell_effects("rg -n shape skills/pstack/how/SKILL.md; wc -l how/SKILL.md", TREE), ([], []))


class InjectedIndexTests(unittest.TestCase):
    def test_injected_index_counts_as_the_owner_read_before_any_event(self):
        trace = chain.Trace(events=[chain.Event(3, "main", "edit", "app.py")])

        stages = run_stages(trace, owner="poteto-mode/SKILL.md", injected=True)

        self.assertEqual((stages["owner_read"], stages["leaf_before_first_edit"]), (True, True))

    def test_without_injection_an_unread_index_is_not_the_owner_read(self):
        trace = chain.Trace(events=[chain.Event(3, "main", "edit", "app.py")])

        stages = run_stages(trace, owner="poteto-mode/SKILL.md", injected=False)

        self.assertEqual((stages["owner_read"], stages["leaf_before_first_edit"]), (False, False))

    def test_first_edit_order_is_not_judged_outside_a_workspace_case(self):
        trace = chain.Trace(events=[chain.Event(3, "main", "edit", "scratch/app.py")])

        self.assertIsNone(run_stages(trace, workspace=False)["leaf_before_first_edit"])


class RunLayoutTests(unittest.TestCase):
    def make(self, root, relative):
        path = root / relative / "trace.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("")
        return path

    def test_cased_layout_names_agent_rule_case_and_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "codex-x"
            (out / "arms").mkdir(parents=True)
            trace = self.make(out, "codex/domain-words/session-tree/amended/runs/session-tree/with_skill/run-2")

            run = chain.locate(trace)

        self.assertEqual((run.out.name, run.agent, run.rule, run.case, run.arm, run.legacy),
                         ("codex-x", "codex", "domain-words", "session-tree", "amended", False))

    def test_layout_from_before_cases_maps_the_rule_to_its_legacy_case(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "claude-y"
            (out / "arms").mkdir(parents=True)
            trace = self.make(out, "claude/preparatory-refactor/current/runs/preparatory-refactor/with_skill")

            run = chain.locate(trace)

        self.assertEqual((run.out.name, run.agent, run.rule, run.case, run.arm, run.legacy),
                         ("claude-y", "claude", "preparatory-refactor", "csv-export", "current", True))

    def test_an_arm_the_build_lists_is_a_run_and_an_unlisted_one_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "codex-z"
            (out / "arms" / "bundle").mkdir(parents=True)
            (out / "arms" / "bundle" / "build.json").write_text(json.dumps({"arms": ["current", "leaf", "leaf+trigger"]}))
            listed = chain.locate(self.make(out, "codex/bundle/csv-export/leaf+trigger/runs/csv-export/with_skill"))
            unlisted = chain.locate(self.make(out, "codex/bundle/csv-export/amended/runs/csv-export/with_skill"))

        self.assertEqual((listed.rule, listed.case, listed.arm), ("bundle", "csv-export", "leaf+trigger"))
        self.assertIsNone(unlisted)

    def test_an_arm_owns_the_first_file_its_patch_changes(self):
        build = {"target": "poteto-mode/playbooks/feature.md",
                 "arm_changes": {"current": [], "leaf+trigger": ["poteto-mode/SKILL.md", "principle-model-the-domain/SKILL.md"]}}

        self.assertEqual(chain.rule_owner("bundle", build, "leaf+trigger"), "poteto-mode/SKILL.md")
        self.assertEqual(chain.rule_owner("bundle", build, "current"), "poteto-mode/playbooks/feature.md")


class InjectionTests(unittest.TestCase):
    def test_wrapper_token_and_listed_slash_command_mean_injected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "entry").mkdir()
            (out / "entry" / "claude").write_text("#!/bin/sh\n{ printf '%s ' /poteto-mode; cat; } | claude-project-only \"$@\"\n")
            run = chain.RunDir(out, "claude", "r", "c", "amended", out, False)

            listed = chain.injection(run, "claude", "poteto-mode", chain.Trace(slash_commands=("poteto-mode",)))
            unlisted = chain.injection(run, "claude", "poteto-mode", chain.Trace(slash_commands=("how",)))
            single = chain.injection(run, "claude", "skill", chain.Trace(slash_commands=("poteto-mode",)))

        self.assertEqual((listed, unlisted, single), (True, False, False))

    def test_codex_workspace_wrapper_passes_the_dollar_token(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "entry").mkdir()
            (out / "entry" / "codex-workspace").write_text("exec python3 workspace.py wrap --token '$poteto-mode' --discovery .agents/skills -- codex-project-only \"$@\"\n")
            run = chain.RunDir(out, "codex", "r", "c", "amended", out, False)

            self.assertTrue(chain.injection(run, "codex", "poteto-mode", chain.Trace()))

    def test_sandbox_wrapper_passes_the_token(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "entry").mkdir()
            (out / "entry" / "codex-sbx").write_text("exec python3 sandbox.py wrap --agent codex --token '$poteto-mode' --discovery .agents/skills -- \"$@\"\n")
            run = chain.RunDir(out, "codex", "r", "c", "leaf", out, False)

            self.assertTrue(chain.injection(run, "codex", "poteto-mode", chain.Trace()))


class PrincipleIndexTests(unittest.TestCase):
    def test_every_principle_in_the_shipped_index_is_parsed(self):
        index = chain.principle_index((chain.screen.REPO / "skills" / "poteto-mode" / "SKILL.md").read_text())

        self.assertEqual((len(index), index["principle-model-the-domain"]), (23, "Model the Domain"))


def make_run(directory, agent, fixture, transcripts=True):
    """A screen.py --out dir around one fixture: a stub mounted tree, a
    build.json whose owner is the Feature playbook, the fixture's trace in the
    run dir, and its harvest in the parallel harvest tree."""
    out = Path(directory) / "out"
    arm = out / "arms" / "domain-words" / "session-tree" / "amended" / "skills"
    for path in TREE:
        (arm / path).parent.mkdir(parents=True, exist_ok=True)
        (arm / path).write_text(FEATURE if path.endswith("feature.md") else "line\n" * 10)
    (out / "arms" / "domain-words" / "build.json").write_text(json.dumps({
        "entry": "poteto-mode", "target": "poteto-mode/playbooks/feature.md",
        "cases": {"session-tree": {"workspace": {"repo": "omnigent"}}},
    }))
    work = out / agent / "domain-words" / "session-tree" / "amended"
    run = work / "runs" / "session-tree" / "with_skill"
    run.mkdir(parents=True)
    shutil.copy(FIXTURES / fixture / "run" / "trace.jsonl", run / "trace.jsonl")
    harvest = work / "harvest" / "session-tree" / "with_skill"
    harvest.mkdir(parents=True)
    if transcripts:
        shutil.copytree(FIXTURES / fixture / "harvest" / "transcripts", harvest / "transcripts")
    return run / "trace.jsonl"


def analyze(fixture, agent, transcripts=True):
    with tempfile.TemporaryDirectory() as directory:
        return chain.analyze(make_run(directory, agent, fixture, transcripts), PRINCIPLES)


class ClaudeSandboxHarvestTests(unittest.TestCase):
    """A synthetic Claude sandbox run, written to the shape the sandbox harvests
    (no paid Claude sandbox run exists yet). The lead reads the Feature
    playbook, calls TaskCreate once, and spawns a poteto-agent and a
    general-purpose delegate. The poteto-agent child reads the index and one
    leaf and edits the checkout. The general-purpose child's one skill read
    errors."""

    def setUp(self):
        self.row = analyze("sbx-claude", "claude")

    def test_child_reads_and_edits_are_the_delegates(self):
        self.assertEqual((self.row["delegation"], self.row["delegate_edits"]), ({
            "spawns": 2, "waits": 0, "delegated": True, "brief_names_shape": True,
            "delegate_reads": ["poteto-mode/SKILL.md", "principle-model-the-domain/SKILL.md"],
        }, ["/workspace/app/src/sessions/tree.py"]))

    def test_child_leaf_read_takes_its_spawn_index(self):
        self.assertEqual(self.row["leaf_reads"], [
            {"path": "principle-model-the-domain/SKILL.md", "index": 5, "actor": "delegate", "partial": False},
        ])

    def test_lead_playbook_read_comes_before_the_delegate_edit(self):
        self.assertEqual((self.row["first_edit"], self.row["leaf_before_first_edit"]), (5, True))

    def test_only_the_poteto_agent_child_got_the_briefing(self):
        self.assertEqual(self.row["delegate_persona"], {
            "spawns": 2, "with_persona": 1, "roles": ["poteto-agent", "general-purpose"],
        })

    def test_offered_task_tool_was_called_once(self):
        self.assertEqual(self.row["worklist_tool"], {"offered": True, "called": True, "calls": 1})

    def test_table_line(self):
        self.assertEqual(chain.table([self.row]).splitlines()[1].split(), [
            "claude", "domain-words", "session-tree", "amended", "1", "UNGRADED", "-", "feature", "0.25", "y", "y", "2/0", "1/1", "0",
        ])


class CodexSandboxHarvestTests(unittest.TestCase):
    """Trimmed real files from a Codex sandbox probe: the exec --json stream
    shows one spawn_agent and one wait, and the child rollout shows a
    poteto-agent that reads the index and unslop with one sed command."""

    def setUp(self):
        self.row = analyze("sbx-codex", "codex")

    def test_child_reads_are_the_delegates(self):
        self.assertEqual((self.row["delegation"], self.row["delegate_edits"]), ({
            "spawns": 1, "waits": 1, "delegated": True, "brief_names_shape": False,
            "delegate_reads": ["poteto-mode/SKILL.md", "unslop/SKILL.md"],
        }, []))
        self.assertEqual(self.row["leaf_reads"], [
            {"path": "unslop/SKILL.md", "index": 3, "actor": "delegate", "partial": False},
        ])

    def test_child_rollout_role_marks_the_briefing(self):
        self.assertEqual(self.row["delegate_persona"], {"spawns": 1, "with_persona": 1, "roles": ["poteto-agent"]})

    def test_no_worklist_tool_evidence(self):
        self.assertEqual(self.row["worklist_tool"], {"offered": None, "called": False, "calls": 0})

    def test_lead_rollout_update_plan_counts_when_the_stream_has_no_todo_list(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = make_run(directory, "codex", "sbx-codex")
            lead = next(trace_path.parents[3].rglob("rollout-*6671-*.jsonl"))
            with lead.open("a") as handle:
                handle.write(json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "update_plan", "arguments": json.dumps({"plan": [{"step": "`how` over the affected subsystem", "status": "pending"}]})}}) + "\n")
                handle.write(json.dumps({"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "await tools.update_plan({plan: []});"}}) + "\n")
            row = chain.analyze(trace_path, PRINCIPLES)

        self.assertEqual((row["worklist_tool"], row["worklist"]["tool_called"]), ({"offered": True, "called": True, "calls": 2}, True))

    def test_table_line(self):
        self.assertEqual(chain.table([self.row]).splitlines()[1].split(), [
            "codex", "domain-words", "session-tree", "amended", "1", "UNGRADED", "-", "-", "-", "-", "-", "1/1", "0/0", "0",
        ])


class NoTranscriptsTests(unittest.TestCase):
    def test_a_harvest_without_transcripts_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = make_run(directory, "claude", "sbx-claude", transcripts=False)
            with_harvest = chain.analyze(trace_path, PRINCIPLES)
            shutil.rmtree(trace_path.parents[3] / "harvest")
            without = chain.analyze(trace_path, PRINCIPLES)

        self.assertEqual(with_harvest, without)
        self.assertEqual((without["delegation"], without["delegate_edits"], without["leaf_reads"], without["first_edit"], without["delegate_persona"]), (
            {"spawns": 2, "waits": 0, "delegated": True, "brief_names_shape": True, "delegate_reads": []},
            [], [], None, {"spawns": 2, "with_persona": 1, "roles": ["poteto-agent", "general-purpose"]},
        ))

    def test_codex_without_transcripts_sees_the_spawn_but_no_role(self):
        row = analyze("sbx-codex", "codex", transcripts=False)

        self.assertEqual((row["delegation"]["delegate_reads"], row["delegate_persona"]), ([], {"spawns": 1, "with_persona": 0, "roles": [None]}))


class AttachTests(unittest.TestCase):
    def test_child_transcript_replaces_the_delegate_records_the_lead_stream_echoed(self):
        trace = chain.parse_claude((FIXTURES / "claude-trace.jsonl").read_text().splitlines(), TREE)
        child = chain.Child("toolu_01J9z92p2dNEHL3MvAXDA43K", [chain.Event(4, "delegate", "edit", "src/tree.py")], {})

        chain.attach(trace, [child])

        self.assertEqual([(event.index, event.sub, event.path) for event in trace.events if event.kind == "edit"], [(8, (4,), "src/tree.py")])

    def test_a_briefing_pasted_into_a_general_purpose_brief_counts(self):
        body = "You are operating as poteto-mode's full agent style\nfor one scoped unit. Read the index."

        self.assertEqual((chain.has_persona(body), chain.has_persona("Run the tests.")), (True, False))


class FixtureLinesAreRealJsonTests(unittest.TestCase):
    def test_every_fixture_line_parses(self):
        for name in ("claude-trace.jsonl", "codex-trace.jsonl"):
            for line in (FIXTURES / name).read_text().splitlines():
                json.loads(line)

    def test_every_harvest_fixture_line_parses(self):
        paths = sorted(FIXTURES.glob("sbx-*/**/*.jsonl"))
        for path in paths:
            for line in path.read_text().splitlines():
                json.loads(line)

        self.assertEqual(len(paths), 7)


if __name__ == "__main__":
    unittest.main()
