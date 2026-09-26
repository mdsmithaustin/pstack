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


SKILLS = chain.screen.REPO / "skills"
SKILL_NAMES = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}
PLAYBOOKS = {name: (SKILLS / "poteto-mode" / "playbooks" / f"{name}.md").read_text() for name in ("feature", "refactoring")}


def shipped_stages(trace, case, owner):
    return chain.stages(trace, case=case, owner=owner, injected=True, playbook_texts=PLAYBOOKS,
                        principles=PRINCIPLES, workspace=True, skill_names=SKILL_NAMES)


class StepSpecTests(unittest.TestCase):
    def test_refactoring_steps_keep_a_five_word_identity_and_every_pointer(self):
        self.assertEqual([(step.identity, step.pointers) for step in chain.step_specs(PLAYBOOKS["refactoring"], SKILL_NAMES)], [
            ("pin the behavior contract first", ("how",)),
            ("name the structure the code", ("principle-model-the-domain",)),
            ("name the target shape", ("principle-foundational-thinking", "principle-redesign-from-first-principles", "architect")),
            ("subtract before you add", ("principle-subtract-before-you-add", "principle-laziness-protocol")),
            ("move in small behavior-preserving steps", ("principle-migrate-callers-then-delete-legacy-apis",)),
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
        worklist = shipped_stages(trace, "harness-families", "poteto-mode/playbooks/refactoring.md")["worklist"]

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
