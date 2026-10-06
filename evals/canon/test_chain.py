import importlib.util
import json
import re
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

    def test_a_delegate_denial_the_lead_echoes_counts_once_with_its_transcript(self):
        lines = (FIXTURES / "claude-trace.jsonl").read_text().splitlines()
        child = chain.parse_claude_child([json.dumps({"type": "user", "message": {"role": "user", "content": "Implement the sessions tree command."}}),
                                          lines[10], lines[12]], {"toolUseId": "toolu_01J9z92p2dNEHL3MvAXDA43K", "agentType": "general-purpose"}, TREE)
        trace = chain.attach(self.trace, [child])

        self.assertEqual([(event.actor, event.text) for event in trace.events if event.kind == "denied"], [("main", "Bash"), ("delegate", "Bash")])

    def test_reply_cites_two_principles_whose_leaves_the_lead_never_read(self):
        self.assertEqual(self.stages["citations"], {
            "cited": ["principle-prove-it-works", "principle-test-behavior-not-implementation"],
            "unread": ["principle-prove-it-works", "principle-test-behavior-not-implementation"],
            "only_read": False,
        })

    def test_the_run_has_no_worklist_tool_to_call(self):
        self.assertEqual({key: self.stages["worklist"][key] for key in ("tool_offered", "carrier", "valid_carrier", "steps_listed", "steps_total", "pointer_fraction")}, {
            "tool_offered": False, "carrier": "none", "valid_carrier": False, "steps_listed": 0, "steps_total": 4, "pointer_fraction": None,
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
        self.assertEqual({key: self.stages["worklist"][key] for key in ("tool_offered", "carrier", "valid_carrier", "steps_listed", "verbatim_fraction")}, {
            "tool_offered": None, "carrier": "message", "valid_carrier": True, "steps_listed": 0, "verbatim_fraction": 0.0,
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

    def test_file_change_keyed_by_path_is_an_edit(self):
        line = json.dumps({"type": "item.completed", "item": {"id": "item_9", "type": "file_change", "status": "completed",
                                                              "changes": {"/w/app/tree.py": {"type": "update"}, "/tmp/scratch.md": {"type": "add"}}}})

        self.assertEqual(chain.parse_codex([line], TREE, "/w/app").events, [chain.Event(0, "main", "edit", "/w/app/tree.py")])


class CodexTodoListTests(unittest.TestCase):
    """A Codex exec --json run that reads the Feature playbook and keeps its
    four steps on the todo_list tool; only the completed item counts."""

    def test_completed_todo_list_is_one_tool_worklist_of_every_step(self):
        stages = run_stages(chain.parse_codex((FIXTURES / "codex-todo-list.jsonl").read_text().splitlines(), TREE))

        self.assertEqual(({key: stages["worklist"][key] for key in ("tool_offered", "carrier", "valid_carrier", "steps_listed", "steps_total", "verbatim_fraction")}, stages["worklist_tool"]), (
            {"tool_offered": True, "carrier": "tool", "valid_carrier": True, "steps_listed": 4, "steps_total": 4, "verbatim_fraction": 1.0},
            {"offered": True, "called": True, "calls": 1},
        ))


class ShellEffectsTests(unittest.TestCase):
    def test_greater_than_inside_a_quoted_script_is_not_a_write(self):
        self.assertEqual(chain.shell_effects("""python3 -c "print(len(x) > 3)" """, TREE), ([], []))

    def test_redirect_outside_quotes_is_a_write(self):
        self.assertEqual(chain.shell_effects("echo hi > notes.txt", TREE), ([], ["notes.txt"]))

    def test_cp_writes_only_its_destination(self):
        self.assertEqual(chain.shell_effects("cp -p src/tree.py backup.py", TREE), ([], ["backup.py"]))

    def test_for_loop_reads_every_word(self):
        reads, _ = chain.shell_effects(
            "/bin/zsh -lc 'for n in how architect; do cat skills/pstack/$n/SKILL.md; done'", TREE)

        self.assertEqual(reads, [("how/SKILL.md", False), ("architect/SKILL.md", False)])

    def test_cd_then_relative_path_resolves(self):
        reads, _ = chain.shell_effects("cd .claude/skills/poteto-mode && cat playbooks/refactoring.md", TREE)

        self.assertEqual(reads, [("poteto-mode/playbooks/refactoring.md", False)])

    def test_writes_that_land_outside_the_checkout_are_not_edits(self):
        def edits(command):
            line = json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": command, "exit_code": 0}})
            return [event.path for event in chain.parse_codex([line], TREE, "/w/app").events if event.kind == "edit"]

        self.assertEqual([edits(command) for command in (
            "tmpclean=$(mktemp /tmp/scratch_clean_XXXX.py) && printf 'x = 1\\n' > \"$tmpclean\" && rm -f \"$tmpfile\" \"$tmpclean\"",
            "scratch=$(mktemp -d)/scratch_debugger.py\nprintf 'def f():\\n    breakpoint()\\n' > \"$scratch\"\nrm -rf \"$(dirname \"$scratch\")\"",
            "probe_dir=$(mktemp -d /tmp/no-debugger-review.XXXXXX); probe_file=\"$probe_dir/probe.py\"; printf '%s\\n' 'import pdb' > \"$probe_file\"",
            "cd /tmp && cat > sanity.mjs <<'EOF'\nconsole.log('ALL PASS')\nEOF\nnode sanity.mjs",
            "printf 'x\\n' > ~/notes.txt",
            "cd src && printf 'x\\n' > tree_notes.py",
            "echo hi > notes.txt",
        )], [[], [], [], [], [], ["src/tree_notes.py"], ["notes.txt"]])

    def test_a_cd_the_command_cannot_resolve_keeps_later_writes_as_edits(self):
        self.assertEqual([chain.shell_effects(command, TREE)[1] for command in (
            'cd "$(git rev-parse --show-toplevel)" && cp a.py b.py',
            'cd "$ROOT" && sed -i s/a/b/ src/x.py',
            "(cd /tmp && echo x > scratch.txt); echo y > b.py",
        )], [["b.py"], ["src/x.py"], ["scratch.txt", "b.py"]])

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
        in_workspace = run_stages(trace, owner="poteto-mode/SKILL.md", injected=True, workspace=True)

        self.assertEqual((run_stages(trace, workspace=False)["leaf_before_first_edit"], in_workspace["leaf_before_first_edit"]),
                         (None, True))


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

    def test_the_stub_keeps_the_rule_target_instead_of_its_first_cut_file(self):
        build = {"target": "poteto-mode/SKILL.md",
                 "arm_changes": {"current": [], "stub": ["architect/SKILL.md", "arena/SKILL.md", "poteto-mode/SKILL.md"]}}

        self.assertEqual(chain.rule_owner("stub-rule", build, "stub"), "poteto-mode/SKILL.md")


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
            (out / "entry" / "codex-workspace").write_text("exec python3 host.py wrap --agent codex --workspace --token '$poteto-mode' --discovery .agents/skills -- codex-project-only \"$@\"\n")
            run = chain.RunDir(out, "codex", "r", "c", "amended", out, False)

            self.assertIs(chain.injection(run, "codex", "poteto-mode", chain.Trace()), True)

    def test_sandbox_wrapper_passes_the_token(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "entry").mkdir()
            (out / "entry" / "codex-sbx").write_text("exec python3 sandbox.py wrap --agent codex --token '$poteto-mode' --discovery .agents/skills -- \"$@\"\n")
            run = chain.RunDir(out, "codex", "r", "c", "leaf", out, False)

            self.assertIs(chain.injection(run, "codex", "poteto-mode", chain.Trace()), True)


class PrincipleIndexTests(unittest.TestCase):
    def test_every_principle_in_the_shipped_index_is_parsed(self):
        text = (chain.screen.REPO / "skills" / "poteto-mode" / "SKILL.md").read_text()
        section = text.split("## Principles", 1)[1].split("## Autonomy", 1)[0]
        expected = set(re.findall(r"\*\*(principle-[a-z-]+)\*\*", section))

        index = chain.principle_index(text)

        self.assertEqual((set(index), index["principle-model-the-domain"]), (expected, "Model the Domain"))


def make_run(directory, agent, fixture, transcripts=True, tree=TREE, case="session-tree"):
    """A screen.py --out dir around one fixture: a stub mounted tree, the
    fixture's build.json or else one whose owner is the Feature playbook, the
    fixture's trace in the run dir, its harvest in the parallel harvest tree,
    and its judge.json in the arm's work dir."""
    source = FIXTURES / fixture
    out = Path(directory) / "out"
    arm = out / "arms" / "domain-words" / case / "amended" / "skills"
    for path in tree:
        (arm / path).parent.mkdir(parents=True, exist_ok=True)
        (arm / path).write_text(FEATURE if path.endswith("feature.md") else "line\n" * 10)
    build = source / "build.json"
    (out / "arms" / "domain-words" / "build.json").write_text(build.read_text() if build.is_file() else json.dumps({
        "entry": "poteto-mode", "target": "poteto-mode/playbooks/feature.md",
        "cases": {"session-tree": {"workspace": {"repo": "omnigent"}}},
    }))
    work = out / agent / "domain-words" / case / "amended"
    run = work / "runs" / case / "with_skill"
    run.mkdir(parents=True)
    shutil.copy(source / "run" / "trace.jsonl", run / "trace.jsonl")
    harvest = work / "harvest" / case / "with_skill"
    harvest.mkdir(parents=True)
    if transcripts:
        shutil.copytree(source / "harvest" / "transcripts", harvest / "transcripts")
    for name in ("workspace.diff", "workspace.json"):
        if (source / "harvest" / name).is_file():
            shutil.copy(source / "harvest" / name, harvest / name)
    if (source / "judge.json").is_file():
        shutil.copy(source / "judge.json", work / "judge.json")
    return run / "trace.jsonl"


def analyze(fixture, agent, transcripts=True, tree=TREE, case="session-tree"):
    with tempfile.TemporaryDirectory() as directory:
        return chain.analyze(make_run(directory, agent, fixture, transcripts, tree, case), PRINCIPLES)


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

    def test_a_denied_child_read_is_counted_and_a_lead_read_that_failed_is_not(self):
        review = analyze("sbx-claude-review", "claude", tree=REVIEW_TREE, case="pr-review")

        self.assertEqual((self.row["tools_denied"], review["tools_denied"]), (1, 0))

    def test_table_line(self):
        self.assertEqual(chain.table([self.row]).splitlines()[1].split(), [
            "claude", "domain-words", "session-tree", "amended", "1", "UNGRADED", "-", "feature", "0.25", "y", "y", "2/0", "1/1", "1",
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


class CodexRealChildRolloutTests(unittest.TestCase):
    """A trimmed real child rollout harvested from a Codex 0.157 sandbox run
    (codex-smoke-separate-contexts-2, the harness-families/leaf arm's
    migrate_callers delegate). Its own session_meta at ordinal 0 marks it a
    poteto-agent subagent forked from the lead thread; its history replay
    then repeats the LEAD's own session_meta at ordinal 1, the way
    history_mode: paginated actually does it. A parser that keeps whichever
    session_meta it sees last would read this child as the lead itself."""

    def setUp(self):
        path = FIXTURES / "sbx-codex-delegates" / "harvest" / "transcripts" / "codex" / "sessions" / "2026" / "09" / "25" / "rollout-2026-09-25T14-42-40-01a0d904-b881-71b1-b94c-06828c0f72e8.jsonl"
        self.meta, self.child = chain.parse_codex_rollout(path.read_text().splitlines(), TREE)

    def test_the_lead_session_meta_further_down_the_file_does_not_win(self):
        self.assertEqual(self.meta.get("id"), "01a0d904-b881-71b1-b94c-06828c0f72e8")
        self.assertEqual(self.meta.get("parent_thread_id"), "01a0d901-50dc-76d1-b766-0d529d47c7c5")

    def test_is_a_child_with_its_role_and_path(self):
        self.assertTrue(chain.is_codex_child(self.meta))
        self.assertEqual((chain.codex_role(self.meta), chain.codex_path(self.meta)), ("poteto-agent", "/root/migrate_callers"))

    def test_reads_and_the_file_change_are_delegate_events(self):
        self.assertEqual([(event.kind, event.path) for event in self.child.events if event.kind in ("read", "edit")], [
            ("read", "unslop/SKILL.md"), ("read", "principle-laziness-protocol/SKILL.md"),
            ("edit", "/workspace/app/src/sessions/tree.py"),
        ])

    def test_role_alone_marks_the_persona_even_though_the_briefing_is_not_its_first_developer_message(self):
        self.assertIs(self.child.persona, True)


class CodexDelegateFanOutTests(unittest.TestCase):
    """A synthetic lead (0.157's exec --json stream: shell reads, two waits,
    never a visible spawn) fanned out to two harvested children: the real
    trimmed poteto-agent from CodexRealChildRolloutTests, which edits a file,
    and an explorer that only reads."""

    def setUp(self):
        self.row = analyze("sbx-codex-delegates", "codex")

    def test_both_children_are_counted_as_spawns_from_the_harvest_alone(self):
        self.assertEqual(self.row["delegation"], {
            "spawns": 2, "waits": 2, "delegated": True, "brief_names_shape": None,
            "delegate_reads": ["how/SKILL.md", "principle-laziness-protocol/SKILL.md", "unslop/SKILL.md"],
        })

    def test_census_names_each_delegates_role_path_and_whether_it_writes_code(self):
        self.assertEqual(self.row["delegate_census"], [
            {"role": "explorer", "path": "/root/how_harness_families", "code_writing": False, "persona": False, "prescribed": "how explorer"},
            {"role": "poteto-agent", "path": "/root/migrate_callers", "code_writing": True, "persona": True, "prescribed": None},
        ])

    def test_only_the_code_writing_delegate_counts_toward_the_implementation_stage(self):
        self.assertEqual(self.row["delegate_persona"], {"spawns": 2, "with_persona": 1, "roles": ["explorer", "poteto-agent"]})
        self.assertEqual(self.row["implementation_delegate_persona"], {"spawns": 1, "with_persona": 1, "misses": []})
        self.assertTrue(chain.STAGES["implementation delegate ran as poteto-agent"](self.row))

    def test_the_edit_is_attributed_to_the_delegate(self):
        self.assertEqual(self.row["delegate_edits"], ["/workspace/app/src/sessions/tree.py"])


class ImplementationDelegatePersonaStageTests(unittest.TestCase):
    def stage(self, implementers):
        row = {"implementation_delegate_persona": {"spawns": len(implementers), "with_persona": sum(implementers)}}
        return chain.STAGES["implementation delegate ran as poteto-agent"](row)

    def test_no_implementation_delegate_is_not_measured(self):
        self.assertEqual((self.stage([]), self.stage([True])), (None, True))

    def test_an_implementation_delegate_without_the_persona_fails(self):
        self.assertIs(self.stage([False]), False)

    def test_every_implementation_delegate_with_the_persona_passes(self):
        self.assertIs(self.stage([True, True]), True)

    def test_one_of_two_implementation_delegates_without_the_persona_fails(self):
        self.assertIs(self.stage([True, False]), False)


class PrescribedRoleTests(unittest.TestCase):
    def test_comment_sicko_by_role_in_either_spelling(self):
        self.assertEqual((chain.prescribed_by("comment-sicko", ""), chain.prescribed_by("Comment Sicko", "")),
                         ("no-comments comment-sicko", "no-comments comment-sicko"))

    def test_comment_sicko_briefing_pasted_into_a_generic_role(self):
        brief = "# Comment Sicko\n\nMy first output when spawned is exactly this.\n\nYes... Ha ha ha... Yes!"

        self.assertEqual(chain.prescribed_by("general-purpose", brief), "no-comments comment-sicko")

    def test_a_how_explorer_brief_built_from_its_template(self):
        brief = ("You are exploring a codebase to understand how something works. Gather facts.\n\n"
                 "## Question\n\nHow do harness families resolve?")

        self.assertEqual(chain.prescribed_by("general-purpose", brief), "how explorer")

    def test_a_delegate_that_read_the_architect_runner_prompt(self):
        self.assertEqual(chain.prescribed_by("default", "", "/root/design_a", {"architect/references/runner-prompt.md"}), "architect runner")

    def test_an_agent_path_that_names_the_routed_skill(self):
        self.assertEqual((chain.prescribed_by("default", "", "/root/how_harness_family"), chain.prescribed_by("default", "", "/root/showcase")),
                         ("how explorer", None))

    def test_an_arena_runner_named_in_its_brief(self):
        self.assertEqual(chain.prescribed_by("general-purpose", "You are arena runner 2 of 3. Write candidate B."), "arena runner")

    def test_a_generic_implementation_brief_is_not_prescribed(self):
        self.assertEqual((chain.prescribed_by("comment-sicko", ""),
                          chain.prescribed_by("worker", "Implement the consumer migration in omnigent/providers.py.", "/root/consumer_migration")),
                         ("no-comments comment-sicko", None))


class CodexRolesHarvestTests(unittest.TestCase):
    """Trimmed real files from the Codex harness-families leaf run
    (codex-bundle-separate-contexts-harness-harness-families-r2, run 1).
    Codex 0.157 encrypts every spawn brief, so each child's role comes from
    its session_meta, its agent path, and its own reads. how_harness_family
    is a default explorer, design_table a default architect runner that read
    the runner prompt, consumer_migration a worker that edits source, and
    comment_review a Comment Sicko that edits comments."""

    def setUp(self):
        self.row = analyze("sbx-codex-roles", "codex", tree={**TREE, "architect/references/runner-prompt.md": 10})

    def test_census_names_the_routed_role_of_each_delegate(self):
        self.assertEqual([(entry["role"], entry["path"], entry["code_writing"], entry["prescribed"]) for entry in self.row["delegate_census"]], [
            ("default", "/root/how_harness_family", False, "how explorer"),
            ("default", "/root/design_table", False, "architect runner"),
            ("worker", "/root/consumer_migration", True, None),
            ("comment-sicko", "/root/comment_review", True, "no-comments comment-sicko"),
        ])

    def test_the_generic_worker_is_the_one_implementation_miss(self):
        self.assertEqual(self.row["implementation_delegate_persona"], {"spawns": 1, "with_persona": 0, "misses": ["worker"]})
        self.assertIs(chain.STAGES["implementation delegate ran as poteto-agent"](self.row), False)

    def test_role_census(self):
        self.assertEqual(self.row["role_census"], {
            "default": {"spawns": 2, "code_writing": 0, "prescribed": 2, "persona": 0, "implementation_misses": 0},
            "worker": {"spawns": 1, "code_writing": 1, "prescribed": 0, "persona": 0, "implementation_misses": 1},
            "comment-sicko": {"spawns": 1, "code_writing": 1, "prescribed": 1, "persona": 0, "implementation_misses": 0},
        })

    def test_an_encrypted_brief_is_no_brief(self):
        claude_row = analyze("sbx-claude", "claude")

        self.assertEqual((self.row["delegation"]["brief_names_shape"], claude_row["delegation"]["brief_names_shape"]), (None, True))


class ClaudeDelegateFlowTests(unittest.TestCase):
    """A synthetic Claude sandbox run in the real shapes of Claude Code
    2.1: two Explore delegates spawned in the background, each
    answered at once by an "Async agent launched" tool_result and later by a
    <task-notification> user message naming its tool-use-id; then two
    foreground poteto-agent builders, each returning in its Agent
    tool_result. The lead reads the tree builder's file after it returns, runs
    one pytest node id after the test builder returns, and ends."""

    def setUp(self):
        self.row = analyze("sbx-claude-delegates", "claude")

    def test_a_delegate_edit_is_delegated_code(self):
        self.assertIs(self.row["delegated_code"], True)

    def test_one_failing_node_id_after_the_last_edit_is_not_a_wide_run(self):
        self.assertEqual(self.row["full_suite_run"], {
            "last_edit": 11, "ordered": True,
            "test_commands_after": ["uv run pytest tests/test_tree.py::test_nested -q 2>&1 | tail -5"], "wide": False,
        })

    def test_foreground_results_and_background_notifications_are_the_returns(self):
        trace = chain.parse_claude((FIXTURES / "sbx-claude-delegates" / "run" / "trace.jsonl").read_text().splitlines(), TREE)

        self.assertEqual([(event.index, event.text) for event in trace.events if event.kind == "return"], [
            (6, "toolu_01SpawnExploreStore"), (7, "toolu_01SpawnExploreRender"),
            (9, "toolu_01SpawnBuildTree"), (12, "toolu_01SpawnBuildTests"),
        ])

    def test_the_lead_read_the_first_builder_file_and_only_tested_after_the_second(self):
        self.assertEqual(self.row["lead_reviewed_delegate"], {"code_delegates": 2, "reviewed": 1, "all": False, "unordered": 0})

    def test_the_second_background_explorer_was_spawned_before_the_first_returned(self):
        self.assertEqual(self.row["parallel_investigation"], {"investigation_spawns": 2, "max_in_flight": 2, "parallel": True, "unordered": 0})

    def test_the_explorers_were_spawned_before_the_first_builder(self):
        self.assertEqual(self.row["investigation_before_first_edit"],
                         {"first_investigation": 2, "first_lead_edit": None, "first_code_spawn": 8, "before": True})


class ClaudeBackgroundInspectionTests(unittest.TestCase):
    """A trimmed real Claude Code sandbox run of paste-markers. The lead cds
    into apps/desktop, so both background poteto-agent children start there,
    and one of them edits hermes_cli/ outside it. Each child returns in a
    system task_notification record naming its tool_use_id, and the turn it
    resumes opens with an init record whose cwd is apps/desktop. The lead then
    Reads both edited files, reruns pytest, and runs git diff --stat."""

    def setUp(self):
        self.row = analyze("sbx-claude-background", "claude")

    def test_system_task_notifications_are_the_returns(self):
        trace = chain.parse_claude((FIXTURES / "sbx-claude-background" / "run" / "trace.jsonl").read_text().splitlines(), TREE)

        self.assertEqual([(event.index, event.text) for event in trace.events if event.kind == "return"], [
            (6, "toolu_01RKunguWUkRc5SWpSUoZxpd"), (8, "toolu_014FhjSSx43PqfuqRKPCEXfX"),
        ])

    def test_an_edit_outside_the_child_shell_cwd_is_still_in_the_checkout(self):
        root = "/private/var/folders/xx/T/claude-ws-a72s0fdm/"
        self.assertEqual(self.row["delegate_edits"], [root + path for path in (
            "apps/desktop/src/lib/composer-input-sanitize.test.ts", "apps/desktop/src/lib/composer-input-sanitize.ts",
            "hermes_cli/input_sanitize.py", "tests/hermes_cli/test_input_sanitize.py")])

    def test_reads_after_both_notifications_inspect_both_delegates(self):
        self.assertEqual(self.row["lead_reviewed_delegate"], {"code_delegates": 2, "reviewed": 2, "all": True, "unordered": 0})

    def test_a_run_with_only_builders_did_not_investigate_first(self):
        self.assertEqual(self.row["investigation_before_first_edit"],
                         {"first_investigation": None, "first_lead_edit": None, "first_code_spawn": 2, "before": False})


class CodexDelegateFlowTests(unittest.TestCase):
    """A synthetic Codex 0.149 exec --json run, whose stream shows each
    spawn_agent with its child thread and each wait with the child's final
    state: two explorers spawned together and awaited in one wait, then a
    poteto-agent builder whose rollout edits the tree and runs one node id.
    The lead runs git diff and the tests directory after the builder's wait."""

    def setUp(self):
        self.row = analyze("sbx-codex-parallel", "codex")

    def test_a_child_rollout_edit_is_delegated_code(self):
        self.assertIs(self.row["delegated_code"], True)

    def test_a_run_whose_delegate_only_reads_has_no_delegated_code(self):
        self.assertIs(analyze("sbx-codex", "codex")["delegated_code"], False)

    def test_the_lead_tests_directory_after_the_child_node_id_is_a_wide_run(self):
        self.assertEqual(self.row["full_suite_run"], {
            "last_edit": 5, "ordered": True,
            "test_commands_after": ["uv run pytest tests/test_tree.py::test_nested", "uv run pytest -q tests/"], "wide": True,
        })

    def test_a_run_without_edits_has_no_last_edit(self):
        self.assertEqual(analyze("sbx-codex", "codex")["full_suite_run"],
                         {"last_edit": None, "ordered": True, "test_commands_after": [], "wide": None})

    def test_git_diff_after_the_builder_wait_inspects_it(self):
        self.assertEqual(self.row["lead_reviewed_delegate"], {"code_delegates": 1, "reviewed": 1, "all": True, "unordered": 0})

    def test_two_explorers_awaited_in_one_wait_ran_in_parallel(self):
        self.assertEqual(self.row["parallel_investigation"], {"investigation_spawns": 2, "max_in_flight": 2, "parallel": True, "unordered": 0})

    def test_the_explorers_were_spawned_before_the_builder(self):
        self.assertEqual(self.row["investigation_before_first_edit"],
                         {"first_investigation": 2, "first_lead_edit": None, "first_code_spawn": 5, "before": True})

    def test_without_a_wait_the_child_task_complete_is_its_return(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = make_run(directory, "codex", "sbx-codex-parallel")
            lines = trace_path.read_text().splitlines()
            trace_path.write_text("\n".join(line for line in lines if '"id": "item_5"' not in line) + "\n")
            row = chain.analyze(trace_path, PRINCIPLES)

        self.assertEqual(row["lead_reviewed_delegate"], {"code_delegates": 1, "reviewed": 1, "all": True, "unordered": 0})

    def test_a_delegate_whose_spawn_the_stream_never_shows_has_no_lead_order(self):
        row = analyze("sbx-codex-delegates", "codex")

        self.assertEqual((row["lead_reviewed_delegate"], row["parallel_investigation"]), (
            {"code_delegates": 1, "reviewed": 0, "all": None, "unordered": 1},
            {"investigation_spawns": 1, "max_in_flight": 0, "parallel": False, "unordered": 1},
        ))

    def test_an_investigation_with_no_lead_order_is_not_placed_before_the_first_edit(self):
        self.assertEqual(analyze("sbx-codex-delegates", "codex")["investigation_before_first_edit"],
                         {"first_investigation": 12, "first_lead_edit": None, "first_code_spawn": 13, "before": None})

    def test_no_code_writing_delegate_is_not_measured(self):
        self.assertEqual(analyze("sbx-codex", "codex")["lead_reviewed_delegate"], {"code_delegates": 0, "reviewed": 0, "all": None, "unordered": 0})

    def test_edits_of_a_child_whose_spawn_the_stream_never_shows_cannot_be_ordered(self):
        self.assertEqual(analyze("sbx-codex-delegates", "codex")["full_suite_run"],
                         {"last_edit": 13, "ordered": False, "test_commands_after": [], "wide": None})


class CodexTimestampOrderTests(unittest.TestCase):
    """A trimmed real Codex 0.157 sandbox run of no-debugger-lint, whose
    stream shows no spawn and names no child in a wait. Its harvest holds the
    lead rollout and eight child rollouts, every line timestamped. A
    poteto-agent child edits four files and finishes at 22:00:00, a
    comment-sicko child edits lint_no_debugger.py at 22:00:25 and finishes at
    22:00:54, and at 22:01:27 the lead reads lint_no_debugger.py and runs
    pytest over tests/dev/lint."""

    def setUp(self):
        self.row = analyze("sbx-codex-timestamps", "codex")

    def test_reads_after_each_child_task_complete_inspect_both_code_writers(self):
        self.assertEqual(self.row["lead_reviewed_delegate"], {"code_delegates": 2, "reviewed": 2, "all": True, "unordered": 0})

    def test_the_lead_pytest_after_the_comment_sicko_edit_is_a_wide_run(self):
        suite = self.row["full_suite_run"]

        first = "sed -n '1,240p' dev/lint/lint_no_debugger.py && uv run --no-sync pytest -q tests/dev/lint &&"
        self.assertEqual((suite["ordered"], suite["wide"], suite["test_commands_after"][0][:len(first)]), (True, True, first))

    def test_architect_runners_are_not_investigation_and_the_two_explorers_ran_apart(self):
        self.assertEqual(self.row["parallel_investigation"], {"investigation_spawns": 2, "max_in_flight": 1, "parallel": False, "unordered": 0})

    def test_without_the_lead_rollout_the_children_stay_unordered(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = make_run(directory, "codex", "sbx-codex-timestamps")
            harvest = chain.screen.harvest_dir(trace_path.parent)
            next(harvest.rglob("rollout-*-01a0e4da-7a83-77b3-8b58-c80d2299db2b.jsonl")).unlink()
            row = chain.analyze(trace_path, PRINCIPLES)

        self.assertEqual(row["lead_reviewed_delegate"], {"code_delegates": 2, "reviewed": 0, "all": None, "unordered": 2})


class DelegateFlowMarkdownTests(unittest.TestCase):
    def test_each_stage_has_a_rate_line_per_agent(self):
        rows = [analyze("sbx-claude-delegates", "claude"), analyze("sbx-codex-parallel", "codex"), analyze("sbx-codex-delegates", "codex")]
        names = ("delegate wrote code", "lead inspected code-writing delegate's work (all)", "delegated investigation", "parallel investigation spawns",
                 "investigation before first edit", "wide test run after last edit")

        self.assertEqual([line for line in chain.markdown(rows).splitlines()[:len(chain.STAGES) + 3] if line.split(" | ")[0][2:] in names], [
            "| delegate wrote code | 1/1 | 2/2 |",
            "| lead inspected code-writing delegate's work (all) | 0/1 | 1/1 |",
            "| delegated investigation | 1/1 | 2/2 |",
            "| parallel investigation spawns | 1/1 | 1/2 |",
            "| investigation before first edit | 1/1 | 1/1 |",
            "| wide test run after last edit | 0/1 | 1/1 |",
        ])


class InspectionWindowTests(unittest.TestCase):
    """The lead's inspection of a code-writing delegate counts only between the
    delegate's return and the lead's final message."""

    def stage(self, *events):
        spawn = chain.Event(1, "main", "spawn")
        trace = chain.Trace(events=[spawn, *events], spawns={"t1": chain.Spawn(spawn, code_writing=True, edits=frozenset({"/w/app/src/tree.py"}))})
        return run_stages(trace)["lead_reviewed_delegate"]["reviewed"]

    def test_a_read_before_the_return_or_after_the_final_message_does_not_count(self):
        self.assertEqual((
            self.stage(chain.Event(2, "main", "view", "src/tree.py"), chain.Event(3, "main", "return", text="t1"), chain.Event(4, "main", "message", text="Done.")),
            self.stage(chain.Event(3, "main", "return", text="t1"), chain.Event(4, "main", "message", text="Done."), chain.Event(5, "main", "shell", text="git status")),
            self.stage(chain.Event(3, "main", "return", text="t1"), chain.Event(4, "main", "shell", text="sed -n '1,40p' src/tree.py"), chain.Event(5, "main", "message", text="Done.")),
        ), (0, 0, 1))

    def test_shell_reads_of_the_edited_file_and_git_inspection_count(self):
        self.assertEqual([chain.reviews(chain.Event(0, "main", "shell", text=command), {"/w/app/src/tree.py"}) for command in (
            "cat src/tree.py", "head -20 app/src/tree.py | nl", "rg -n tree src/tree.py", "git --no-pager diff -- src",
            "git -C /w/app show HEAD", "git status --short", "cat src/other.py", "rg -n src/tree.py docs", "git log -3",
        )], [True, True, True, True, True, True, False, False, False])

    def test_sequential_foreground_explorers_are_not_parallel(self):
        first, second = chain.Event(1, "main", "spawn"), chain.Event(3, "main", "spawn")
        trace = chain.Trace(events=[first, chain.Event(2, "main", "return", text="a"), second, chain.Event(4, "main", "return", text="b")],
                            spawns={"a": chain.Spawn(first, role="Explore"), "b": chain.Spawn(second, role="Explore")})

        self.assertEqual(run_stages(trace)["parallel_investigation"], {"investigation_spawns": 2, "max_in_flight": 1, "parallel": False, "unordered": 0})


class CodexNestedInvestigationTests(unittest.TestCase):
    """A trimmed real Codex 0.157 sandbox run of no-debugger-lint
    (r3-codex-cut-feature-review, current, run 1) with four of its ten
    children. how_lint_subsystem spawns its own direct_explainer and waits on
    it. architect_candidate_1 and architect_candidate_2 read the how
    explainer prompt while grounding their designs."""

    def setUp(self):
        self.row = analyze("sbx-codex-nested", "codex", tree={
            **TREE, "architect/references/runner-prompt.md": 10,
            "how/references/explorer-prompt.md": 10, "how/references/explainer-prompt.md": 10,
        })

    def test_an_architect_path_decides_the_role_over_a_how_template_read(self):
        self.assertEqual([(entry["path"], entry["prescribed"]) for entry in self.row["delegate_census"]], [
            ("/root/how_lint_subsystem", "how explorer"),
            ("/root/how_lint_subsystem/direct_explainer", "how explorer"),
            ("/root/architect_candidate_1", "architect runner"),
            ("/root/architect_candidate_2", "architect runner"),
        ])

    def test_a_how_explorer_waiting_on_its_own_child_is_one_investigation(self):
        self.assertEqual(self.row["parallel_investigation"], {"investigation_spawns": 1, "max_in_flight": 1, "parallel": False, "unordered": 0})


class InvestigationSpawnTests(unittest.TestCase):
    """Spawns placed at one lead index, as Codex children are, each returned
    at a later index."""

    def stage(self, *spawns):
        events = [chain.Event(1, "main", "spawn", sub=(n,)) for n in range(len(spawns))]
        returns = [chain.Event(2 + n, "main", "return", text=f"s{n}") for n in range(len(spawns))]
        keyed = {f"s{n}": chain.Spawn(event, role=role, path=path) for n, (event, (role, path)) in enumerate(zip(events, spawns))}
        row = run_stages(chain.Trace(events=[*events, *returns], spawns=keyed))
        return row["parallel_investigation"], row["delegated_investigation"]

    def test_read_only_architect_candidates_are_not_investigation(self):
        self.assertEqual(self.stage(*[("poteto-agent", f"/root/architect_{name}") for name in ("ast", "table", "boundary")]), (
            {"investigation_spawns": 0, "max_in_flight": 0, "parallel": False, "unordered": 0}, False))

    def test_how_roles_and_unprescribed_explore_types_are_investigation(self):
        self.assertEqual(self.stage(
            ("explorer", "/root/how_custom_lint"), ("Explore", None), ("explorer", "/root/scan_callers"),
            ("explorer", "/root/architect_judge"), ("general-purpose", None), ("poteto-agent", "/root/design_a"),
        ), ({"investigation_spawns": 3, "max_in_flight": 3, "parallel": True, "unordered": 0}, True))


class InvestigationBeforeFirstEditTests(unittest.TestCase):
    """One explorer spawned at index 3, after a lead edit or a code-writing
    spawn at index 2, or with nothing before it."""

    def stage(self, before):
        explore = chain.Event(3, "main", "spawn")
        spawns = {"x": chain.Spawn(explore, role="Explore")}
        if before == "spawn":
            spawns["b"] = chain.Spawn(chain.Event(2, "main", "spawn"), role="poteto-agent", code_writing=True)
        events = sorted([spawn.event for spawn in spawns.values()] + [chain.Event(2 if before == "edit" else 4, "main", "edit", "/w/app/src/tree.py")],
                        key=chain.order)
        return run_stages(chain.Trace(events=events, spawns=spawns))["investigation_before_first_edit"]

    def test_a_lead_edit_or_code_spawn_before_the_first_explorer_is_not_investigation_first(self):
        self.assertEqual((self.stage("edit"), self.stage("spawn"), self.stage(None)), (
            {"first_investigation": 3, "first_lead_edit": 2, "first_code_spawn": None, "before": False},
            {"first_investigation": 3, "first_lead_edit": 4, "first_code_spawn": 2, "before": False},
            {"first_investigation": 3, "first_lead_edit": 4, "first_code_spawn": None, "before": True},
        ))


class TestCommandTests(unittest.TestCase):
    def test_runners_and_their_scope(self):
        commands = [
            "pytest", "python -m pytest tests/test_tree.py", "uv run --frozen pytest tests/test_tree.py::test_nested -q",
            "uv run pytest -k nested", "uv run pytest tests -k nested", "python3 -m pytest 'tests/test_tree.py::TestTree::test_a' tests/test_tree.py::test_b",
            "python3 -m unittest test_chain -v", "python -m unittest tests.test_tree.TreeTests.test_nested", "python -m unittest -k nested",
            "python -m unittest discover -s tests", "npm test", "pnpm test -- --watch=false", "yarn test", "node --test",
            "go test ./...", "cargo test", "just test", "UV_OFFLINE=1 uv run pytest -x --tb=short tests/test_tree.py::test_nested 2>&1 | tail -3",
            "git diff", "python3 tools/check-links.py", "rg -n pytest",
        ]

        self.assertEqual([chain.test_scope(command) for command in commands], [
            "wide", "wide", "single",
            "single", "wide", "single",
            "wide", "single", "single",
            "wide", "wide", "wide", "wide", "wide",
            "wide", "wide", "wide", "single",
            None, None, None,
        ])

    def test_the_hermes_pytest_wrapper_and_npm_with_a_prefix_are_test_runs(self):
        commands = [
            "scripts/run_tests.sh tests/hermes_cli/test_input_sanitize.py; test_rc=$?",
            "scripts/run_tests.sh tests/hermes_cli/test_input_sanitize.py::test_glued -q",
            "npm --prefix apps/desktop test -- src/lib/composer-input-sanitize.test.ts",
        ]

        self.assertEqual([chain.test_scope(command) for command in commands], ["wide", "single", "wide"])

    def test_a_compound_command_is_as_wide_as_its_widest_test_run(self):
        self.assertEqual(chain.test_scope("cd app && pytest tests/test_a.py::test_x && pytest tests"), "wide")


SKILLS = chain.screen.REPO / "skills"
SKILL_NAMES = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}
PLAYBOOKS = {name: (SKILLS / "poteto-mode" / "playbooks" / f"{name}.md").read_text() for name in ("feature", "refactoring")}


def shipped_stages(trace, case, owner, playbook_texts=PLAYBOOKS):
    return chain.stages(trace, case=case, owner=owner, injected=True, playbook_texts=playbook_texts,
                        principles=PRINCIPLES, workspace=True, skill_names=SKILL_NAMES)


class StepSpecTests(unittest.TestCase):
    def test_refactoring_steps_keep_a_five_word_identity_and_every_pointer(self):
        self.assertEqual([(step.identity, step.pointers) for step in chain.step_specs(PLAYBOOKS["refactoring"], SKILL_NAMES)], [
            ("pin the behavior contract first", ("how",)),
            ("name the structure the code", ("principle-model-the-domain",)),
            ("name the target shape", ("principle-foundational-thinking", "principle-redesign-from-first-principles", "architect")),
            ("subtract before you add", ("principle-subtract-before-you-add", "principle-laziness-protocol")),
            ("move in small behavior-preserving steps", ("principle-migrate-callers-then-delete-legacy-apis", "pstack-harness")),
            ("prove behavior is unchanged on", ("principle-prove-it-works",)),
            ("confirm the change is worth", ("principle-minimize-reader-load",)),
            ("rebase into small ordered commits", ("sequence-verifiable-units",)),
        ])

    def test_a_pointer_on_an_indented_line_belongs_to_its_step_and_a_non_skill_is_no_pointer(self):
        text = "1. Delegate with `sonnet` per **pstack-harness**.\n   - Split per the **separate-before-serializing-shared-state** principle skill.\n2. Run **Opening a PR**.\n"

        self.assertEqual(chain.step_specs(text, SKILL_NAMES), [
            chain.Step("delegate with sonnet per pstack-harness", ("pstack-harness", "separate-before-serializing-shared-state")),
            chain.Step("run opening a pr", ()),
        ])

    def test_message_items_join_continuation_lines(self):
        self.assertEqual(chain.message_items("Worklist:\n\n1. Pin it.\n   Then test.\n- Ship.\n"), ["Pin it. Then test.", "Ship."])

    def test_a_code_mode_update_plan_call_lists_its_steps(self):
        self.assertEqual(chain.exec_plan_text('await tools.update_plan({plan: [{step: "Pin the behavior", status: "pending"}, {"step": \'Name the shape\'}]});'),
                         "Pin the behavior\nName the shape")

    def test_an_escaped_quote_stays_inside_its_step(self):
        self.assertEqual(chain.exec_plan_text(r'tools.update_plan({plan: [{step: "Say \"done\" once"}]})'), r'Say \"done\" once')

    def test_an_unclosed_step_of_many_escapes_returns_the_source(self):
        source = 'tools.update_plan({plan: [{step: "' + "\\a" * 200

        self.assertEqual(chain.exec_plan_text(source), source)


class ClaudeMultiResultTests(unittest.TestCase):
    """A trimmed real Claude sandbox run (claude-bundle-one-name-tags-
    sessions-by-tag-r3, leaf, run 2). The lead ended two turns while its
    delegates ran in the background, so the stream holds three result
    events, the last being the answer. Nine TaskCreate calls carry the
    Feature steps, reworded in places."""

    def setUp(self):
        self.lines = (FIXTURES / "claude-multi-result.jsonl").read_text().splitlines()
        self.trace = chain.parse_claude(self.lines, TREE)

    def test_the_last_result_is_the_answer(self):
        self.assertEqual((self.trace.result_events, self.trace.final[:60]),
                         (3, "You can now list sessions by label, for example everything w"))

    def test_task_create_carries_seven_of_eight_steps_and_three_of_eight_pointers(self):
        worklist = shipped_stages(self.trace, "sessions-by-tag", "poteto-mode/playbooks/feature.md")["worklist"]

        self.assertEqual({key: worklist[key] for key in ("tool_offered", "carrier", "valid_carrier", "steps_listed", "steps_total", "pointer_fraction")}, {
            "tool_offered": True, "carrier": "tool", "valid_carrier": True, "steps_listed": 7, "steps_total": 8, "pointer_fraction": 0.38,
        })
        self.assertEqual([(step["listed"], step["kept"]) for step in worklist["steps"]], [
            (True, ["how"]), (True, ["architect"]), (False, []), (True, []), (True, []), (True, []), (True, ["interrogate"]), (True, []),
        ])

    def test_a_harvested_raw_stream_is_read_in_place_of_the_harness_trace(self):
        filtered = [line for line in self.lines if json.loads(line)["type"] != "result"] + [self.lines[-1]]
        with tempfile.TemporaryDirectory() as directory:
            trace_path = make_run(directory, "claude", "sbx-claude", transcripts=False)
            trace_path.write_text("\n".join(filtered) + "\n")
            alone = chain.analyze(trace_path, PRINCIPLES)
            (trace_path.parents[3] / "harvest" / "session-tree" / "with_skill" / "raw-stream.jsonl").write_text("\n".join(self.lines) + "\n")
            raw = chain.analyze(trace_path, PRINCIPLES)

        self.assertEqual((alone["result_events"], raw["result_events"]), (1, 3))


class CodexMessageWorklistTests(unittest.TestCase):
    """The same Codex run's lead: it reads the Refactoring playbook and posts
    its eight steps, verbatim, as a numbered message."""

    def test_every_step_and_every_pointer_is_kept(self):
        trace = chain.parse_codex((FIXTURES / "sbx-codex-roles" / "run" / "trace.jsonl").read_text().splitlines(), TREE)
        seen = {**PLAYBOOKS, "refactoring": (FIXTURES / "sbx-codex-roles" / "refactoring.md").read_text()}
        worklist = shipped_stages(trace, "harness-families", "poteto-mode/playbooks/refactoring.md", seen)["worklist"]

        self.assertEqual({key: worklist[key] for key in ("tool_offered", "carrier", "valid_carrier", "steps_listed", "steps_total", "pointer_fraction")}, {
            "tool_offered": None, "carrier": "message", "valid_carrier": True, "steps_listed": 8, "steps_total": 8, "pointer_fraction": 1.0,
        })


class WorklistCarrierTests(unittest.TestCase):
    def worklist(self, offered, events):
        trace = chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md"), *events], worklist_tool_offered=offered)
        return run_stages(trace)["worklist"]

    def test_a_message_list_is_invalid_when_a_tool_was_offered(self):
        self.assertFalse(self.worklist(True, [chain.Event(1, "main", "message", text="Worklist:\n1. `how` over the affected subsystem")])["valid_carrier"])

    def test_a_message_list_is_valid_after_the_tool_rejected_a_call(self):
        worklist = self.worklist(True, [chain.Event(1, "main", "worklist-rejected", text="`how` over the affected subsystem"),
                                        chain.Event(2, "main", "message", text="Worklist:\n1. `how` over the affected subsystem")])

        self.assertEqual((worklist["carrier"], worklist["tool_rejected"], worklist["valid_carrier"], worklist["steps_listed"]), ("message", True, True, 1))

    def test_a_message_that_names_two_steps_is_a_worklist_without_the_word(self):
        worklist = self.worklist(None, [chain.Event(1, "main", "message", text="Plan:\n1. how over the affected subsystem\n2. architect for parallel design exploration")])

        self.assertEqual((worklist["carrier"], worklist["valid_carrier"], worklist["steps_listed"]), ("message", True, 2))

    def test_no_list_is_no_valid_carrier(self):
        self.assertFalse(self.worklist(None, [])["valid_carrier"])


def playbook_text(name):
    return (SKILLS / "poteto-mode" / "playbooks" / f"{name}.md").read_text()


def numbered_steps(text):
    return [re.sub(r"^\d+\.\s+", "", line) for line in text.splitlines() if re.match(r"^\d+\.\s", line)]


class PlaybookOpeningTests(unittest.TestCase):
    def test_a_bold_lead_and_the_prose_after_it_are_each_an_identity(self):
        names = ("feature", "bug-fix", "refactoring", "orchestrate", "multi-phase-plan", "research")
        self.assertEqual([chain.playbook_opening(playbook_text(name)) for name in names], [
            ("you own the design", "delegate implementation"),
            ("you own this task", "delegate investigation and the fix"),
            ("you own the contract", "distinct from feature"),
            ("you own the program", "for a whole project handed"),
            ("you own the plan", "the plan is the deliverable"),
            ("use for external",),
        ])

    def test_a_bold_lead_with_nothing_after_it_is_the_only_identity(self):
        self.assertEqual(chain.playbook_opening(playbook_text("authoring-a-skill")), ("you own the skill's voice",))

    def test_a_playbook_without_a_bold_lead_opens_with_its_first_clause(self):
        self.assertEqual([chain.playbook_opening("Use for X, then Y. More.\n" + FEATURE), chain.playbook_opening(FEATURE)],
                         [("use for x",), None])

    def test_steps_with_nothing_before_them_have_no_opening(self):
        self.assertEqual([chain.playbook_opening(FEATURE), chain.playbook_opening("Lead.\n" + FEATURE)], [None, ("lead",)])

    def test_punctuation_outside_the_bold_span_is_skipped_before_the_trailing_clause(self):
        self.assertEqual([chain.playbook_opening(f"**You own X**{tail}\n" + FEATURE) for tail in (". Delegate the fix.", ": delegate the fix.", " Delegate the fix.")],
                         [("you own x", "delegate the fix")] * 3)

    def test_a_bold_lead_followed_only_by_punctuation_has_no_empty_identity(self):
        self.assertEqual([chain.playbook_opening(f"**You own X**{tail}\n" + FEATURE) for tail in (".", ":", " . ")], [("you own x",)] * 3)

    def test_a_dash_or_ellipsis_between_the_bold_span_and_the_trailing_clause_is_skipped(self):
        self.assertEqual([chain.playbook_opening(f"**You own X**{tail}\n" + FEATURE) for tail in (" \u2014 Delegate the fix.", " \u2013 Delegate the fix.", "\u2026 Delegate the fix.")],
                         [("you own x", "delegate the fix")] * 3)

    def test_a_bold_lead_followed_only_by_a_dash_or_ellipsis_has_no_wordless_identity(self):
        self.assertEqual([chain.playbook_opening(f"**You own X**{tail}\n" + FEATURE) for tail in (" \u2014", " \u2013", "\u2026", " $$")],
                         [("you own x",)] * 4)

    def test_an_exclamation_or_question_mark_ends_the_opening_clause(self):
        self.assertEqual([chain.playbook_opening(f"{line}\n" + FEATURE) for line in ("**You own this task! Plan, review.**", "**You own this task? Plan, review.**", "Use for X! More.")],
                         [("you own this task",), ("you own this task",), ("use for x",)])

    def test_a_spaced_em_dash_ends_the_opening_clause(self):
        self.assertEqual(chain.first_clause("you own this task \u2014 plan, review"), "you own this task")

    def test_a_worklist_without_the_trailing_clause_fails_item_zero_when_punctuation_trails_the_bold_span(self):
        text = "**You own X**. Delegate the fix.\n" + FEATURE
        trace = lambda item: chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md"),
                                                 chain.Event(1, "main", "worklist", text=f"{item}\n" + "\n".join(numbered_steps(text)))])
        kept = [shipped_stages(trace(item), "sessions-by-tag", "poteto-mode/playbooks/feature.md", {"feature": text})["worklist"]["opening"]
                for item in ("You own X.", "You own X. Delegate the fix.")]

        self.assertEqual(kept, [{"identities": ["you own x", "delegate the fix"], "kept": False},
                                {"identities": ["you own x", "delegate the fix"], "kept": True}])

    def test_curly_quotes_fold_to_ascii_on_both_sides(self):
        self.assertEqual([chain.normalize("The skill\u2019s \u201cvoice\u201d"), chain.normalize("The skill's \"voice\"")],
                         ["the skill's \"voice\"", "the skill's \"voice\""])

    def test_no_shipped_playbook_opens_with_the_read_in_full_sentence(self):
        names = sorted(path.stem for path in (SKILLS / "poteto-mode" / "playbooks").glob("*.md"))
        openings = {name: chain.playbook_opening(playbook_text(name)) for name in names}

        self.assertEqual([name for name, opening in openings.items()
                          if not opening or any(identity.startswith("read this playbook") for identity in opening)], [])


class WorklistOpeningTests(unittest.TestCase):
    """Item 0 of a worklist is the matched playbook's opening prose. A run can
    copy every numbered step and still drop it, which the step stages score as
    a full list."""

    def worklist(self, name, lines, carrier="tool"):
        text = playbook_text(name)
        trace = chain.Trace(events=[chain.Event(0, "main", "read", f"poteto-mode/playbooks/{name}.md"),
                                    chain.Event(1, "main", "worklist" if carrier == "tool" else "message", text="\n".join(lines))])
        return shipped_stages(trace, "sessions-by-tag", f"poteto-mode/playbooks/{name}.md", {name: text})["worklist"]

    def test_every_step_without_the_opening_prose_fails_item_zero(self):
        worklist = self.worklist("feature", numbered_steps(playbook_text("feature")))

        self.assertEqual((worklist["steps_listed"], worklist["steps_total"], worklist["opening"]),
                         (8, 8, {"identities": ["you own the design", "delegate implementation"], "kept": False}))

    def test_the_opening_line_ahead_of_every_step_passes_item_zero(self):
        text = playbook_text("feature")
        opening = next(line for line in text.splitlines() if line.startswith("**You own"))
        worklist = self.worklist("feature", [opening, *numbered_steps(text)])

        self.assertEqual((worklist["steps_listed"], worklist["opening"]),
                         (8, {"identities": ["you own the design", "delegate implementation"], "kept": True}))

    def test_a_lead_that_drops_the_delegate_sentence_fails_item_zero(self):
        text = playbook_text("bug-fix")
        steps = numbered_steps(text)
        lead = "**You own this task. Plan, review, verify.**"
        full = f"{lead} Delegate investigation and the fix to subagents, stay in the lead."

        self.assertEqual([self.worklist("bug-fix", [line, *steps])["opening"]["kept"] for line in (lead, full)], [False, True])

    def test_a_reworded_item_that_keeps_both_clauses_passes(self):
        worklist = self.worklist("bug-fix", ["Worklist:", "0. You own this task: plan, review, verify. Delegate investigation and the fix, stay lead.",
                                             "1. Reproduce it yourself"], carrier="message")

        self.assertEqual(worklist["opening"], {"identities": ["you own this task", "delegate investigation and the fix"], "kept": True})

    def test_curly_quotes_in_the_worklist_still_name_the_lead(self):
        worklist = self.worklist("authoring-a-skill", ["You own the skill\u2019s voice."])

        self.assertEqual(worklist["opening"], {"identities": ["you own the skill's voice"], "kept": True})

    def test_no_worklist_fails_item_zero(self):
        trace = chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md")])

        self.assertEqual(shipped_stages(trace, "sessions-by-tag", "poteto-mode/playbooks/feature.md")["worklist"]["opening"],
                         {"identities": ["you own the design", "delegate implementation"], "kept": False})

    def test_a_playbook_with_no_numbered_steps_has_no_worklist_to_open(self):
        openings = [self.worklist(name, ["Use when the matched playbook produces a PR."])["opening"] for name in ("opening-a-pr", "research")]

        self.assertEqual(openings, [None, {"identities": ["use for external"], "kept": False}])

    def test_a_playbook_with_nothing_before_step_one_has_no_item_zero(self):
        trace = chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md")])

        def opening(text):
            return chain.stages(trace, case="session-tree", owner="poteto-mode/playbooks/feature.md", injected=True,
                                playbook_texts={"feature": text}, principles=PRINCIPLES, workspace=True)["worklist"]["opening"]

        self.assertEqual([opening(FEATURE), opening("Lead.\n" + FEATURE)], [None, {"identities": ["lead"], "kept": False}])

    def test_a_run_that_read_no_playbook_has_no_item_zero(self):
        text = playbook_text("feature")
        read = chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md")])
        unread = chain.Trace(events=[chain.Event(0, "main", "read", "how/SKILL.md")])

        self.assertEqual([shipped_stages(trace, "sessions-by-tag", "poteto-mode/playbooks/feature.md", {"feature": text})["worklist"]["opening"]
                          for trace in (read, unread)],
                         [{"identities": ["you own the design", "delegate implementation"], "kept": False}, None])

    def test_a_playbook_missing_from_the_tree_has_no_item_zero(self):
        text = playbook_text("feature")
        trace = chain.Trace(events=[chain.Event(0, "main", "read", "poteto-mode/playbooks/feature.md")])

        self.assertEqual([shipped_stages(trace, "sessions-by-tag", "poteto-mode/playbooks/feature.md", texts)["worklist"]["opening"]
                          for texts in ({"feature": text}, {})],
                         [{"identities": ["you own the design", "delegate implementation"], "kept": False}, None])

    def test_the_stage_reads_the_item_zero_verdict_and_skips_runs_without_one(self):
        stage = chain.STAGES["playbook opening prose listed"]

        self.assertEqual([stage({"worklist": {"opening": opening}}) for opening in ({"identities": ["x"], "kept": True}, {"identities": ["x"], "kept": False}, None)],
                         [True, False, None])


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


REVIEW_TREE = {**TREE, **{path: 10 for path in (
    "poteto-mode/playbooks/investigation.md", "interrogate/SKILL.md",
    "interrogate/references/code-quality-review.md", "interrogate/references/reviewer-prompt.md",
    "architect/references/design-red-flags.md",
)}}


class ClaudeReviewTests(unittest.TestCase):
    """A synthetic Claude review of pr-42. The lead loads interrogate, fails
    to read the design red flags, reads the code quality reference, cats the
    Prove It Works leaf and how in one command, spawns a general-purpose
    reviewer that reads the interrogate reviewer prompt and one leaf, then
    rereads the code quality reference. The harvest shows two touched files
    and a moved head."""

    def setUp(self):
        self.review = analyze("sbx-claude-review", "claude", tree=REVIEW_TREE, case="pr-review")["review"]

    def test_route_is_the_lead_completed_reads_in_order(self):
        self.assertEqual((self.review["route"], self.review["primary"], self.review["route_reads"]), (
            ["interrogate", "interrogate/code-quality-review", "how"], "interrogate",
            [{"route": "interrogate", "index": 1}, {"route": "interrogate/code-quality-review", "index": 5}, {"route": "how", "index": 7}],
        ))

    def test_principle_leaves_split_by_reader(self):
        self.assertEqual(self.review["principle_leaves"], {
            "lead": ["principle-prove-it-works"], "delegate": ["principle-test-behavior-not-implementation"],
        })

    def test_the_reviewer_delegate_holds_the_interrogate_role(self):
        self.assertEqual(self.review["delegated"], {"delegated": True, "spawns": 1, "roles": ["interrogate reviewer"]})

    def test_a_changed_checkout_and_moved_head_modify_the_pr(self):
        self.assertEqual((self.review["pr_modified"], self.review["pr_paths"], self.review["head_moved"]), (
            True, ["src/sessions/tree.py", "tests/test_tree.py"], True,
        ))

    def test_verdict_comes_from_the_judge(self):
        self.assertEqual((self.review["branch"], self.review["verdict"]), ("pr-42", {"combined": "FOUND", "calibrated": True}))


class CodexReviewTests(unittest.TestCase):
    """A synthetic Codex review of pr-42. The lead reads the Investigation
    playbook, the design red flags, and the Model the Domain leaf, then spawns
    one child at /root/interrogate_reviewer that reads Laziness Protocol. The
    checkout is untouched and the head stays at the PR ref."""

    def setUp(self):
        self.row = analyze("sbx-codex-review", "codex", tree=REVIEW_TREE, case="pr-review")

    def test_review_of_an_untouched_pr(self):
        self.assertEqual(self.row["review"], {
            "branch": "pr-42",
            "route": ["investigation", "architect-design-red-flags"],
            "primary": "investigation",
            "route_reads": [{"route": "investigation", "index": 1}, {"route": "architect-design-red-flags", "index": 2}],
            "principle_leaves": {"lead": ["principle-model-the-domain"], "delegate": ["principle-laziness-protocol"]},
            "delegated": {"delegated": True, "spawns": 1, "roles": ["interrogate reviewer"]},
            "pr_modified": False,
            "pr_paths": [],
            "head_moved": False,
            "verdict": {"combined": "MISSED", "calibrated": False},
        })

    def test_markdown_review_section(self):
        claude = analyze("sbx-claude-review", "claude", tree=REVIEW_TREE, case="pr-review")
        lines = chain.markdown([claude, self.row, analyze("sbx-claude", "claude")]).splitlines()
        start = lines.index("claude review (1 runs)")

        self.assertEqual(lines[start - 2:], [
            "Review cases. The route is the review skill files the lead read, in order; the primary route is the first.", "",
            "claude review (1 runs)", "", "| stage | runs |", "|---|---|",
            "| primary route interrogate | 1/1 |",
            "| read an interrogate reference | 1/1 |", "| read a principle leaf | 1/1 |", "| delegated | 1/1 |",
            "| pr modified | 1/1 |", "| head moved | 1/1 |", "| delegate roles | interrogate reviewer 1 |", "",
            "| primary route | FOUND | PARTIAL | MISSED | FALSE_ALARM | CLEAN | unjudged |", "|---|---|---|---|---|---|---|",
            "| interrogate | 1 | 0 | 0 | 0 | 0 | 0 |", "",
            "codex review (1 runs)", "", "| stage | runs |", "|---|---|",
            "| primary route investigation | 1/1 |",
            "| read an interrogate reference | 0/1 |", "| read a principle leaf | 1/1 |", "| delegated | 1/1 |",
            "| pr modified | 0/1 |", "| head moved | 0/1 |", "| delegate roles | interrogate reviewer 1 |", "",
            "| primary route | FOUND | PARTIAL | MISSED | FALSE_ALARM | CLEAN | unjudged |", "|---|---|---|---|---|---|---|",
            "| investigation | 0 | 0 | 1 | 0 | 0 | 0 |",
        ])

    def test_a_build_run_has_no_review(self):
        self.assertEqual((self.row["review"]["primary"], analyze("sbx-codex", "codex")["review"]), ("investigation", None))


if __name__ == "__main__":
    unittest.main()
