import json
import sys
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import live
import oracles
from harnesses import grok
from oracles import FAIL, INCONCLUSIVE, PASS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRACES = HERE / "testdata" / "traces"
CASES = HERE / "cases"
FIXTURES = HERE / "fixtures"
HISTORIES = HERE / "histories"
MEANINGS = ("eval", "evals", "evaluation", "judge", "experiment", "rubric", "score", "compare",
            "benchmark", "candidate", "arena", "promise", "promises", "oracle", "verdict")
GUIDE_WORDS = {"route-research": {"compare"}, "research-run": {"compare"}, "route-eval": {"eval"}, "eval-run": {"eval"},
               "arena-run": {"arena"}, "arena-second-opinion-run": {"arena"}}


def load_case(cid):
    case = json.loads((CASES / cid / "case.json").read_text(encoding="utf-8"))
    case["id"] = cid
    return case


def load_trace(name):
    return json.loads((TRACES / name).read_text(encoding="utf-8"))


def grade(pid, trace, case, project=None):
    return oracles.check(pid, trace, case, project)


def feature_case(**over):
    case = load_case("feature-run")
    case.update(over)
    return case


def minimal(events=(), worklist=(), spawns=(), final_reply="", harness="claude-code", exit_code=0, **extra):
    trace = {"harness": harness, "model": "m", "effort": "high", "exit_code": exit_code, "entry": "injected",
             "events": list(events), "worklist": list(worklist), "spawns": list(spawns),
             "files_read": [], "final_reply": final_reply}
    trace.update(extra)
    return trace


def read(seq, rel):
    return {"seq": seq, "kind": "tool_call", "name": "Read", "input": {"file_path": f"/w/.claude/skills/{rel}"}}


def bash(seq, command, ok=True, head=""):
    return [{"seq": seq, "kind": "tool_call", "name": "Bash", "input": {"command": command}},
            {"seq": seq + 1, "kind": "tool_result", "name": "Bash", "ok": ok, "output_head": head}]


def edit(seq, path):
    return {"seq": seq, "kind": "tool_call", "name": "Edit", "input": {"file_path": path}}


def text(seq, body):
    return {"seq": seq, "kind": "text", "text": body}


def feature_items(skills_root=ROOT / "skills"):
    shape = oracles.playbook_shape("feature", skills_root)
    items = [{"text": shape["prose"][0], "state": "pending"}]
    items += [{"text": f"{s['n']}. {s['text']}", "state": "pending"} for s in shape["steps"]]
    return items


class ProbeTraces(unittest.TestCase):
    def verdicts(self, name, case=None):
        trace = load_trace(name)
        case = case or feature_case()
        return {pid: grade(pid, trace, case)["verdict"] for pid in case["promises"]}

    def test_claude_medium_no_worklist_fails_worklist_promises(self):
        v = self.verdicts("claude-code-feature-1.json")
        self.assertEqual(v["worklist-opens-with-playbook-steps"], FAIL)
        self.assertEqual(v["worklist-in-native-task-tool"], FAIL)
        self.assertEqual(v["skipped-step-stays-in-worklist"], INCONCLUSIVE)
        self.assertEqual(v["design-ladder-spares-small-changes"], PASS)

    def test_claude_high_with_task_tools_passes_worklist_promises(self):
        v = self.verdicts("claude-code-feature-2.json")
        self.assertEqual(v["worklist-opens-with-playbook-steps"], PASS)
        self.assertEqual(v["worklist-in-native-task-tool"], PASS)
        self.assertEqual(v["skipped-step-stays-in-worklist"], PASS)
        self.assertEqual(v["claude-effort-applies-via-effort-agents"], PASS)
        self.assertEqual(v["persona-delivery-hermes-grok"], INCONCLUSIVE)
        self.assertEqual(v["design-ladder-spares-small-changes"], PASS)

    def test_claude_high_reply_quotes_executed_commands_with_outputs(self):
        trace = load_trace("claude-code-feature-2.json")
        result = grade("reply-carries-commands-and-outputs", trace, feature_case())
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][:2], ["commands quoted in reply: 4", "with a matching output line: 2"])

    def test_routing_passes_on_every_probe_run(self):
        case = load_case("route-feature")
        for name in sorted(p.name for p in TRACES.glob("*.json")):
            with self.subTest(trace=name):
                result = grade("feature-prompt-routes-to-feature", load_trace(name), case)
                self.assertEqual(result["verdict"], PASS, result)

    def test_codex_runs_were_killed_so_reply_promises_are_inconclusive(self):
        v = self.verdicts("codex-feature-1.json")
        self.assertEqual(v["reply-carries-commands-and-outputs"], INCONCLUSIVE)
        self.assertEqual(v["prove-it-works-checks-real-artifact"], INCONCLUSIVE)
        self.assertEqual(v["worklist-opens-with-playbook-steps"], PASS)
        self.assertEqual(v["worklist-in-native-task-tool"], PASS)
        self.assertEqual(v["claude-effort-applies-via-effort-agents"], INCONCLUSIVE)

    def test_hermes_worklist_opens_with_feature_steps(self):
        for name in ("hermes-feature-1.json", "hermes-feature-2.json"):
            with self.subTest(trace=name):
                v = self.verdicts(name)
                self.assertEqual(v["worklist-opens-with-playbook-steps"], PASS)
                self.assertEqual(v["worklist-in-native-task-tool"], PASS)
                self.assertEqual(v["design-ladder-spares-small-changes"], FAIL)

    def test_hermes_run_two_marks_skipped_steps_in_item_text(self):
        v = self.verdicts("hermes-feature-2.json")
        self.assertEqual(v["skipped-step-stays-in-worklist"], PASS)

    def test_hermes_persona_delivery_shows_briefing_but_not_announcement(self):
        v = self.verdicts("hermes-feature-1.json")
        self.assertEqual(v["persona-delivery-hermes-grok"], INCONCLUSIVE)

    def test_grok_worklist_native_and_killed(self):
        v = self.verdicts("grok-feature-1.json")
        self.assertEqual(v["worklist-opens-with-playbook-steps"], PASS)
        self.assertEqual(v["worklist-in-native-task-tool"], PASS)
        self.assertEqual(v["reply-carries-commands-and-outputs"], INCONCLUSIVE)
        self.assertEqual(v["design-ladder-spares-small-changes"], FAIL)

    def test_no_probe_run_passes_every_promise(self):
        case = feature_case()
        for name in sorted(p.name for p in TRACES.glob("*.json")):
            with self.subTest(trace=name):
                v = self.verdicts(name, case)
                self.assertIn(FAIL, v.values(), v)

    def test_unknown_promise_is_inconclusive(self):
        result = grade("no-such-promise", load_trace("claude-code-feature-1.json"), feature_case())
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertEqual(result["failures"], ["no oracle for no-such-promise"])


class RoutingOracle(unittest.TestCase):
    def test_other_playbook_first_fails(self):
        trace = minimal(events=[read(0, "poteto-mode/playbooks/bug-fix.md"), read(1, "poteto-mode/playbooks/feature.md")])
        result = grade("feature-prompt-routes-to-feature", trace, load_case("route-feature"))
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["lead opened bug-fix before feature"])

    def test_worklist_alone_identifies_the_playbook(self):
        trace = minimal(worklist=[{"seq": 3, "carrier": "TodoWrite", "items": feature_items()}])
        self.assertEqual(grade("feature-prompt-routes-to-feature", trace, load_case("route-feature"))["verdict"], PASS)

    def test_worklist_of_another_playbook_fails(self):
        shape = oracles.playbook_shape("bug-fix", ROOT / "skills")
        items = [{"text": shape["prose"][0], "state": "pending"}] + [{"text": s["text"], "state": "pending"} for s in shape["steps"]]
        trace = minimal(events=[read(0, "poteto-mode/playbooks/feature.md")], worklist=[{"seq": 3, "carrier": "TodoWrite", "items": items}])
        result = grade("feature-prompt-routes-to-feature", trace, load_case("route-feature"))
        self.assertEqual(result["verdict"], FAIL)

    def test_killed_before_anything_is_inconclusive(self):
        trace = minimal(exit_code=-9)
        self.assertEqual(grade("feature-prompt-routes-to-feature", trace, load_case("route-feature"))["verdict"], INCONCLUSIVE)

    def test_finished_run_with_no_playbook_fails(self):
        trace = minimal(events=bash(0, "ls") + bash(2, "cat README.md") + bash(4, "python3 -m tally sample.txt"))
        self.assertEqual(grade("feature-prompt-routes-to-feature", trace, load_case("route-feature"))["verdict"], FAIL)

    def test_figure_it_out_route(self):
        case = load_case("route-figure-it-out")
        good = minimal(events=[read(0, "figure-it-out/SKILL.md")])
        bad = minimal(events=[read(0, "poteto-mode/playbooks/feature.md"), read(1, "figure-it-out/SKILL.md")])
        self.assertEqual(grade("step-away-routes-to-figure-it-out", good, case)["verdict"], PASS)
        self.assertEqual(grade("step-away-routes-to-figure-it-out", bad, case)["verdict"], FAIL)

    def test_an_in_conversation_run_must_not_route_through_figure_it_out(self):
        case = load_case("route-autonomous-run")
        pid = "in-conversation-run-skips-figure-it-out"
        for first in ("poteto-mode/playbooks/autonomous-run.md", "poteto-mode/playbooks/bug-fix.md"):
            self.assertEqual(grade(pid, minimal(events=[read(0, first)]), case)["verdict"], PASS, first)
        phases = [{"text": t, "state": "pending"} for t in ("Read the Principles section of the poteto-mode skill.", "Phase A: Frame", "Phase B: Design the workflow", "Phase C: Run the loop",
                                                           "Phase D: Keep the audit trail", "Phase E: Verify and hand back")]
        for trace in (minimal(events=[read(0, "figure-it-out/SKILL.md")]),
                      minimal(events=[read(0, "poteto-mode/playbooks/autonomous-run.md")],
                              worklist=[{"seq": 3, "carrier": "TodoWrite", "items": phases}])):
            self.assertEqual(grade(pid, trace, case)["verdict"], FAIL)

    def test_read_only_pin_fails_on_an_edit(self):
        case = load_case("route-investigation")
        trace = minimal(events=[read(0, "poteto-mode/playbooks/investigation.md"), edit(1, "/w/relay/cache.py")])
        result = grade("read-only-phrase-pins-investigation", trace, case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("edited project files"))
        clean = minimal(events=[read(0, "poteto-mode/playbooks/investigation.md")])
        self.assertEqual(grade("read-only-phrase-pins-investigation", clean, case)["verdict"], PASS)

    def test_babysit_check_fails_when_it_loops(self):
        case = load_case("route-babysit-check")
        looping = minimal(events=[read(0, "poteto-mode/playbooks/babysit.md")] + bash(1, "watch-pr 123") + bash(3, "watch-pr 123 --until READY"),
                          final_reply="check mode")
        self.assertEqual(grade("babysit-status-request-no-loop", looping, case)["verdict"], FAIL)
        bare = minimal(events=[read(0, "poteto-mode/playbooks/babysit.md")] + bash(1, "watch-pr --pr 123"), final_reply="check mode: no PR 123")
        self.assertEqual(grade("babysit-status-request-no-loop", bare, case)["verdict"], FAIL)
        retried = minimal(events=[read(0, "poteto-mode/playbooks/babysit.md")] + bash(1, "watch-pr --status-only --pr 123")
                          + bash(3, "watch-pr --status-only --pr 123 > /tmp/wp.out"), final_reply="check mode: exit 7 twice")
        self.assertEqual(grade("babysit-status-request-no-loop", retried, case)["verdict"], PASS)
        named = minimal(events=[read(0, "poteto-mode/playbooks/babysit.md")] + bash(1, "ls scripts/watch-pr/")
                        + bash(3, "watch-pr --status-only --pr 123"), final_reply="check mode")
        self.assertEqual(grade("babysit-status-request-no-loop", named, case)["verdict"], PASS)


class ShellReads(unittest.TestCase):
    def test_a_variable_assigned_in_the_command_resolves_in_a_read(self):
        case = load_case("route-eval")
        trace = minimal(events=bash(0, "cd \"$PWD\"; S=.claude/skills/poteto-mode; cat $S/playbooks/eval.md"))
        self.assertEqual(grade("eval-prompt-routes-to-eval-playbook", trace, case)["verdict"], PASS)


    def test_a_for_loop_over_skill_names_reads_each_leaf(self):
        command = 'cd .claude/skills && for s in principle-prove-it-works principle-laziness-protocol; do echo "=== $s"; cat $s/SKILL.md; done'
        reads = [rel for _, rel in oracles.View(minimal(events=bash(0, command)), load_case("feature-run"), Path("/nonexistent")).event_reads()]
        self.assertEqual(reads, ["principle-prove-it-works/SKILL.md", "principle-laziness-protocol/SKILL.md"])


class ExtractorParity(unittest.TestCase):
    def test_the_oracle_splits_every_playbook_the_way_a_lead_does(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import test_playbook_shape as shape
        for path in shape.PLAYBOOKS:
            with self.subTest(playbook=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(oracles.extract_steps(text), shape.extract(text)[0])


class SteerByDelegate(unittest.TestCase):
    def test_a_delete_delegate_on_the_steer_turn_acts_on_subtract_before_you_add(self):
        case = load_case("principle-steer-run")
        events = [{"seq": 0, "kind": "user", "turn": 0, "text": "add a tsv source"},
                  {"seq": 1, "kind": "user", "turn": 1, "text": "use subtract before you add"},
                  dict(read(2, "principle-subtract-before-you-add/SKILL.md"), turn=1),
                  {"seq": 3, "kind": "user", "turn": 2, "text": "apply prove it works"},
                  dict(read(4, "principle-prove-it-works/SKILL.md"), turn=2),
                  {"seq": 5, "kind": "tool_call", "turn": 2, "name": "Bash", "input": {"command": "python3 -m relay import feeds/sample.json"}}]
        spawn = {"seq": 2, "turn": 1, "tool": "Agent", "description": "Delete dead XML source adapters", "prompt_head": "remove them"}
        trace = minimal(events=events, spawns=[spawn])
        self.assertEqual(grade("principle-name-steers-agent", trace, case)["verdict"], PASS)
        trace = minimal(events=events, spawns=[dict(spawn, description="Add a TSV source")])
        self.assertEqual(grade("principle-name-steers-agent", trace, case)["verdict"], FAIL)
        call = {"seq": 6, "kind": "tool_call", "turn": 1, "name": "Agent", "input": {"description": "Delete dead XML source adapters"}}
        trace = minimal(events=events + [call], spawns=[dict(spawn, seq=6, description=None, prompt_head="Pstack installed skill paths")])
        self.assertEqual(grade("principle-name-steers-agent", trace, case)["verdict"], PASS)


class RuntimeEncoding(unittest.TestCase):
    def test_a_runtime_change_the_reply_explains_encodes_the_constraint(self):
        constraint = "do not remove: the sink needs a trailing newline on every row"
        changes = {"rollup/sink.py": '        self.handle.write(row + "\\n")'}
        self.assertEqual(oracles.encoding_landed(changes, constraint, "Sink.append now adds the trailing newline itself"),
                         "runtime: rollup/sink.py")
        self.assertIsNone(oracles.encoding_landed(changes, constraint, "removed 20 comments"))
        self.assertIsNone(oracles.encoding_landed({"rollup/sink.py": "    for row in rows:"}, constraint,
                                                  "every comment is gone"))
        self.assertIsNone(oracles.encoding_landed({"rollup/export.py": "    return row"}, constraint, "Done."))
        self.assertIsNone(oracles.encoding_landed({"rollup/export.py": "    sink = get_sink()"}, constraint,
                                                  "Sink.append still enforces the trailing newline"))
        self.assertIsNone(oracles.encoding_landed({"rollup/export.py": '    audit.write("done\\n")'}, constraint,
                                                  "Sink.append enforces the trailing newline"))


class BoundaryGuard(unittest.TestCase):
    def test_a_cross_module_feature_needs_the_architect_step(self):
        case = load_case("feature-boundary-run")
        pid = "poteto-mode-triggers-architect-on-boundary-crossing"
        designed = minimal(events=[read(0, "poteto-mode/playbooks/feature.md"), read(1, "architect/SKILL.md"),
                                   read(2, "architect/references/runner-prompt.md")], spawns=[{"seq": s, "tool": "spawn_agent", "x_prompt_encrypted": True} for s in (8, 9)], final_reply="done")
        self.assertEqual(grade(pid, designed, case)["verdict"], PASS)
        skipped = minimal(events=[read(0, "poteto-mode/playbooks/feature.md")] + bash(1, "python3 -m relay import feeds/sample.json"),
                          final_reply="done")
        self.assertEqual(grade(pid, skipped, case)["verdict"], FAIL)
        read_then_skipped = minimal(events=[read(0, "poteto-mode/playbooks/feature.md"), read(1, "architect/SKILL.md")],
                                    final_reply="architect skipped: one module")
        self.assertEqual(grade("design-ladder-spares-small-changes", read_then_skipped, load_case("feature-run"))["verdict"], PASS)


class WorklistOracle(unittest.TestCase):
    def test_taskcreate_accumulation_coalesces_into_one_opening(self):
        items = feature_items()
        snaps = [{"seq": i, "carrier": "TaskCreate", "items": items[: i + 1]} for i in range(len(items))]
        trace = minimal(worklist=snaps)
        result = grade("worklist-opens-with-playbook-steps", trace, feature_case())
        self.assertEqual(result["verdict"], PASS, result)

    def test_bespoke_plan_fails(self):
        items = [{"text": "Read the code", "state": "pending"}, {"text": "Add the flag", "state": "pending"}, {"text": "Test it", "state": "pending"}]
        trace = minimal(worklist=[{"seq": 1, "carrier": "TodoWrite", "items": items}])
        result = grade("worklist-opens-with-playbook-steps", trace, feature_case())
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"][0], "first item is not the playbook's opening prose")

    def test_steps_out_of_order_fail(self):
        items = feature_items()
        items[1], items[4] = items[4], items[1]
        trace = minimal(worklist=[{"seq": 1, "carrier": "TodoWrite", "items": items}])
        result = grade("worklist-opens-with-playbook-steps", trace, feature_case())
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("out of order", result["failures"][0])

    def test_fallback_needs_todo_tools_off(self):
        trace = minimal(worklist=[{"seq": 1, "carrier": "text", "items": feature_items()}])
        self.assertEqual(grade("worklist-falls-back-to-numbered-list", trace, feature_case())["verdict"], INCONCLUSIVE)
        case = load_case("feature-run-no-todo")
        self.assertEqual(grade("worklist-falls-back-to-numbered-list", trace, case)["verdict"], PASS)
        self.assertEqual(grade("worklist-falls-back-to-numbered-list", minimal(), case)["verdict"], FAIL)
        self.assertEqual(grade("worklist-in-native-task-tool", trace, case)["verdict"], INCONCLUSIVE)

    def test_dropped_step_without_marker_fails(self):
        items = feature_items()
        trace = minimal(worklist=[{"seq": 1, "carrier": "TodoWrite", "items": items},
                                  {"seq": 9, "carrier": "TodoWrite", "items": items[:3] + items[4:]}])
        result = grade("skipped-step-stays-in-worklist", trace, feature_case())
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("dropped", result["failures"][0])

    def test_skipped_marker_that_vanishes_fails(self):
        items = feature_items()
        marked = [dict(i) for i in items]
        marked[2]["state"] = "skipped: one file"
        trace = minimal(worklist=[{"seq": 1, "carrier": "TodoWrite", "items": items},
                                  {"seq": 5, "carrier": "TodoWrite", "items": marked},
                                  {"seq": 9, "carrier": "TodoWrite", "items": marked[:2] + marked[3:]}])
        self.assertEqual(grade("skipped-step-stays-in-worklist", trace, feature_case())["verdict"], FAIL)


class ReplyOracles(unittest.TestCase):
    def test_reply_without_commands_fails(self):
        trace = minimal(events=bash(0, "python3 -m tally sample.txt --json", head='[{"word": "the", "count": 4}]'),
                        final_reply="Done. It works now.")
        self.assertEqual(grade("reply-carries-commands-and-outputs", trace, feature_case())["verdict"], FAIL)

    def test_reply_with_command_and_output_passes(self):
        trace = minimal(events=bash(0, "python3 -m tally sample.txt --json", head='[{"word": "the", "count": 4}]'),
                        final_reply='Ran `python3 -m tally sample.txt --json`:\n[{"word": "the", "count": 4}]')
        self.assertEqual(grade("reply-carries-commands-and-outputs", trace, feature_case())["verdict"], PASS)

    def test_inconclusive_wording_required_when_a_check_cannot_run(self):
        events = bash(0, "python3 -m tally sample.txt --json", ok=False, head="ModuleNotFoundError")
        confident = minimal(events=events, final_reply="Both outputs verified.")
        honest = minimal(events=events, final_reply="The JSON check is inconclusive: the module failed to import.")
        ran = minimal(events=bash(0, "python3 -m tally sample.txt", head="4 the"), final_reply="verified")
        self.assertEqual(grade("reply-says-inconclusive-when-check-cannot-run", confident, feature_case())["verdict"], FAIL)
        self.assertEqual(grade("reply-says-inconclusive-when-check-cannot-run", honest, feature_case())["verdict"], PASS)
        self.assertEqual(grade("reply-says-inconclusive-when-check-cannot-run", ran, feature_case())["verdict"], INCONCLUSIVE)

    def test_prove_it_works_needs_a_run_after_the_last_edit(self):
        verified = minimal(events=[edit(0, "/w/tally/__main__.py")] + bash(1, "python3 -m tally sample.txt --json", head="[]"))
        unverified = minimal(events=bash(0, "python3 -m tally sample.txt", head="4 the") + [edit(2, "/w/tally/__main__.py")], final_reply="done")
        self.assertEqual(grade("prove-it-works-checks-real-artifact", verified, feature_case())["verdict"], PASS)
        self.assertEqual(grade("prove-it-works-checks-real-artifact", unverified, feature_case())["verdict"], FAIL)

    def test_principles_named_must_be_read(self):
        unread = minimal(events=[read(0, "principle-prove-it-works/SKILL.md")],
                         final_reply="Laziness Protocol kept the diff to one file. Prove It Works: ran both modes.")
        result = grade("poteto-mode-reads-principles-and-names-applied", unread, feature_case())
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("principle-laziness-protocol", result["failures"][0])
        none = minimal(final_reply="Added the flag.")
        self.assertEqual(grade("poteto-mode-reads-principles-and-names-applied", none, feature_case())["verdict"], FAIL)
        read_all = minimal(events=[read(0, "principle-prove-it-works/SKILL.md")], final_reply="Prove It Works: ran both modes.")
        result = grade("poteto-mode-reads-principles-and-names-applied", read_all, feature_case())
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result["needs_judge"])


class HarnessDelivery(unittest.TestCase):
    def test_effort_without_effort_agent_fails(self):
        trace = minimal(spawns=[{"seq": 1, "tool": "Agent", "subagent_type": "general-purpose", "model": "sonnet", "effort": "high", "persona": "poteto-agent"}])
        result = grade("claude-effort-applies-via-effort-agents", trace, feature_case())
        self.assertEqual(result["verdict"], FAIL)
        trace["spawns"][0]["subagent_type"] = "pstack-effort-high"
        trace["spawns"][0]["observed"] = {"efforts": ["medium"]}
        self.assertEqual(grade("claude-effort-applies-via-effort-agents", trace, feature_case())["verdict"], FAIL)
        trace["spawns"][0]["observed"] = {"efforts": ["high"]}
        self.assertEqual(grade("claude-effort-applies-via-effort-agents", trace, feature_case())["verdict"], PASS)

    def test_effort_promise_not_applicable_elsewhere(self):
        result = grade("claude-effort-applies-via-effort-agents", minimal(harness="codex"), feature_case())
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertTrue(result.get("not_applicable"))

    def test_persona_delivery_on_grok(self):
        spawn = {"seq": 1, "tool": "spawn_subagent", "persona": "poteto-agent", "prompt_head": "Pstack installed skill paths ..."}
        announced = minimal(harness="grok", spawns=[spawn], events=[
            {"seq": 1, "kind": "tool_call", "name": "spawn_subagent", "input": {}},
            {"seq": 2, "kind": "tool_result", "name": "get_command_or_subagent_output", "ok": True, "output_head": "persona: poteto-agent\nDone."}])
        self.assertEqual(grade("persona-delivery-hermes-grok", announced, feature_case())["verdict"], PASS)
        silent = minimal(harness="grok", spawns=[spawn])
        self.assertEqual(grade("persona-delivery-hermes-grok", silent, feature_case())["verdict"], INCONCLUSIVE)
        unbriefed = minimal(harness="grok", spawns=[{"seq": 1, "tool": "spawn_subagent", "persona": "poteto-agent", "prompt_head": "Add the flag."}])
        self.assertEqual(grade("persona-delivery-hermes-grok", unbriefed, feature_case())["verdict"], FAIL)


class ToolResultPairing(unittest.TestCase):
    def view(self, events):
        return oracles.View(minimal(events=events), load_case("bug-fix-run"), None)

    def commands(self, events):
        return [(seq, ok) for seq, _, ok, _ in self.view(events).commands()]

    def test_parallel_calls_pair_with_their_own_results_by_id(self):
        events = [{"seq": 2, "kind": "tool_call", "name": "Bash", "id": "a", "input": {"command": "python3 -m unittest discover -s tests"}},
                  {"seq": 3, "kind": "tool_call", "name": "Bash", "id": "b", "input": {"command": "git status"}},
                  {"seq": 4, "kind": "tool_result", "name": "Bash", "id": "b", "ok": True, "output_head": "clean"},
                  {"seq": 5, "kind": "tool_result", "name": "Bash", "id": "a", "ok": False, "output_head": "FAIL: test_retry"}]
        self.assertEqual(self.commands(events), [(2, False), (3, True)])

    def test_parallel_calls_without_ids_pair_in_order_and_each_result_is_used_once(self):
        events = [{"seq": 2, "kind": "tool_call", "name": "Bash", "input": {"command": "python3 -m unittest discover -s tests"}},
                  {"seq": 3, "kind": "tool_call", "name": "Bash", "input": {"command": "git status"}},
                  {"seq": 4, "kind": "tool_result", "name": "Bash", "ok": False, "output_head": "FAIL: test_retry"},
                  {"seq": 5, "kind": "tool_result", "name": "Bash", "ok": True, "output_head": "clean"}]
        self.assertEqual(self.commands(events), [(2, False), (3, True)])

    def test_a_call_with_no_result_stays_unanswered(self):
        events = [{"seq": 2, "kind": "tool_call", "name": "Bash", "id": "a", "input": {"command": "pytest"}},
                  {"seq": 3, "kind": "tool_result", "name": "Bash", "id": "zzz", "ok": False, "output_head": "other"}]
        self.assertEqual(self.commands(events), [(2, None)])


class FailedReads(unittest.TestCase):
    BRIEF = "architect/references/runner-prompt.md"

    def trace(self, ok, **extra):
        events = [read(0, "poteto-mode/playbooks/feature.md"), {"seq": 1, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "x"},
                  read(2, self.BRIEF), {"seq": 3, "kind": "tool_result", "name": "Read", "ok": ok, "output_head": "x" if ok else "File does not exist"}]
        return minimal(events=events, final_reply="done", spawns=[{"seq": s, "tool": "spawn_agent", "x_prompt_encrypted": True} for s in (8, 9)], **extra)

    def test_a_read_whose_result_failed_is_not_evidence(self):
        case = load_case("feature-boundary-run")
        pid = "poteto-mode-triggers-architect-on-boundary-crossing"
        self.assertEqual(grade(pid, self.trace(True), case)["verdict"], PASS)
        self.assertEqual(grade(pid, self.trace(False), case)["verdict"], FAIL)
        listed = self.trace(False, files_read=[f"/w/.claude/skills/{self.BRIEF}"])
        self.assertEqual(grade(pid, listed, case)["verdict"], FAIL)

    def test_a_killed_runs_last_read_with_no_result_is_not_evidence(self):
        case = load_case("feature-boundary-run")
        pid = "poteto-mode-triggers-architect-on-boundary-crossing"
        unanswered = self.trace(True)
        unanswered["events"].pop()
        self.assertEqual(grade(pid, unanswered, case)["verdict"], PASS)
        unanswered["exit_code"] = 137
        self.assertNotEqual(grade(pid, unanswered, case)["verdict"], PASS)

    def test_a_later_good_read_of_the_same_file_still_counts(self):
        case = load_case("feature-boundary-run")
        retried = self.trace(False)
        retried["events"] += [read(4, self.BRIEF), {"seq": 5, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "x"}]
        self.assertEqual(grade("poteto-mode-triggers-architect-on-boundary-crossing", retried, case)["verdict"], PASS)


class HostSkillContamination(unittest.TestCase):
    def test_a_run_that_touched_host_skills_grades_inconclusive_for_every_promise(self):
        case = load_case("feature-boundary-run")
        events = [read(0, "poteto-mode/playbooks/feature.md"), read(1, "architect/references/runner-prompt.md")]
        hits = ["/Users/someone/.claude/skills"]
        for pid in case["promises"]:
            with self.subTest(pid=pid):
                clean = grade(pid, minimal(events=events, final_reply="done"), case)
                dirty = grade(pid, minimal(events=events, final_reply="done", x_host_skill_hits=hits), case)
                self.assertEqual(dirty["verdict"], INCONCLUSIVE, dirty)
                self.assertTrue(any("host skills" in r for r in dirty["failures"]), dirty)
                self.assertNotEqual(clean["verdict"], INCONCLUSIVE, clean)

    def test_empty_hits_do_not_block_grading(self):
        case = load_case("feature-boundary-run")
        events = [read(0, "poteto-mode/playbooks/feature.md"), read(1, "architect/references/runner-prompt.md")]
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", minimal(events=events, spawns=[{"seq": s, "tool": "spawn_agent", "x_prompt_encrypted": True} for s in (8, 9)], final_reply="done", x_host_skill_hits=[]), case)
        self.assertEqual(result["verdict"], PASS)


class BugFixOracles(unittest.TestCase):
    def test_repro_before_fix(self):
        case = load_case("bug-fix-run")
        good = minimal(events=bash(0, "ROLLUP_BUSY_AFTER=2 python3 -m rollup data/orders.csv out.csv", head="wrote") + [edit(2, "/w/rollup/export.py")])
        bad = minimal(events=[edit(0, "/w/rollup/export.py")] + bash(1, "python3 -m rollup data/orders.csv out.csv"))
        self.assertEqual(grade("bug-fix-reproduces-before-fixing", good, case)["verdict"], PASS)
        self.assertEqual(grade("bug-fix-reproduces-before-fixing", bad, case)["verdict"], FAIL)
        self.assertEqual(grade("bug-fix-reproduces-before-fixing", minimal(exit_code=-9), case)["verdict"], INCONCLUSIVE)

    def test_tdd_order(self):
        case = load_case("bug-fix-run")
        good = minimal(events=[read(0, "poteto-tdd/SKILL.md"), edit(1, "/w/tests/test_export.py")]
                       + bash(2, "python3 -m unittest discover -s tests", ok=False, head="FAIL: test_retry")
                       + [edit(4, "/w/rollup/export.py")] + bash(5, "python3 -m unittest discover -s tests", head="OK"))
        self.assertEqual(grade("bug-fix-uses-poteto-tdd-when-cheap", good, case)["verdict"], PASS)
        fix_first = minimal(events=[edit(0, "/w/rollup/export.py"), edit(1, "/w/tests/test_export.py")] + bash(2, "python3 -m unittest", head="OK"))
        self.assertEqual(grade("bug-fix-uses-poteto-tdd-when-cheap", fix_first, case)["verdict"], FAIL)

    def test_steering_needs_turn_markers(self):
        case = load_case("steer-repro-run")
        unmarked = minimal(events=[edit(0, "/w/rollup/export.py")])
        self.assertEqual(grade("steering-prompt-redirects-run", unmarked, case)["verdict"], INCONCLUSIVE)
        marked = minimal(events=[dict(edit(0, "/w/rollup/export.py"), turn=1), dict(text(1, "Reproduced only."), turn=1)])
        self.assertEqual(grade("steering-prompt-redirects-run", marked, case)["verdict"], FAIL)
        stopped = minimal(events=[dict(text(1, "Reproduced. Stopping before any fix."), turn=1)])
        self.assertEqual(grade("steering-prompt-redirects-run", stopped, case)["verdict"], PASS)


class HowWhyOracles(unittest.TestCase):
    def test_narrow_how_fails_on_explorers(self):
        case = load_case("how-run")
        explorer = {"seq": 1, "tool": "Agent", "persona": "how explorer", "prompt_head": "You are exploring a codebase"}
        self.assertEqual(grade("how-narrow-question-no-explorers", minimal(spawns=[explorer], final_reply="x"), case)["verdict"], FAIL)
        self.assertEqual(grade("how-narrow-question-no-explorers", minimal(final_reply="x"), case)["verdict"], PASS)

    def test_wide_how_wants_two_to_four_explorers_in_one_message(self):
        case = load_case("how-wide-run")
        explorers = [{"seq": i, "tool": "Agent", "persona": "how explorer", "prompt_head": "You are exploring a codebase. Read-only."} for i in (1, 2, 3)]
        explainer = {"seq": 9, "tool": "Agent", "persona": "how explainer", "prompt_head": "You are writing an architectural explanation"}
        events = [{"seq": i, "kind": "tool_call", "name": "Agent", "input": {}} for i in (1, 2, 3)]
        self.assertEqual(grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=explorers + [explainer], final_reply="x"), case)["verdict"], PASS)
        self.assertEqual(grade("how-fans-out-explorers-for-big-subsystem", minimal(spawns=[explainer], final_reply="x"), case)["verdict"], FAIL)
        sequential = events[:1] + [text(2, "waiting")] + events[1:]
        self.assertEqual(grade("how-fans-out-explorers-for-big-subsystem", minimal(events=sequential, spawns=explorers + [explainer]), case)["verdict"], FAIL)

    def test_how_then_why_order(self):
        case = load_case("how-then-why-run")
        good = minimal(events=[read(0, "how/SKILL.md"), read(1, "why/SKILL.md")], final_reply="Sources consulted: git log")
        bad = minimal(events=[read(0, "why/SKILL.md"), read(1, "how/SKILL.md")], final_reply="Sources consulted: git log")
        self.assertEqual(grade("how-then-why-sequence-honored", good, case)["verdict"], PASS)
        self.assertEqual(grade("how-then-why-sequence-honored", bad, case)["verdict"], FAIL)
        self.assertEqual(grade("why-then-how-composition", bad, load_case("why-then-how-run"))["verdict"], PASS)

    def test_why_report_citations(self):
        case = load_case("why-run")
        cited = minimal(final_reply="82c90a8 `retry: raise the limit to five` names the 41 s rebuild. It appears to still hold.\n### Sources Consulted\n- git log\n- issue tracker: not available")
        self.assertEqual(grade("why-reports-cited-history", cited, case)["verdict"], PASS)
        self.assertEqual(grade("why-reports-null-results", cited, case)["verdict"], PASS)
        self.assertEqual(grade("how-why-reports-name-sources-searched", cited, case)["verdict"], PASS)
        bare = minimal(final_reply="The limit is five because of timeouts.")
        self.assertEqual(grade("why-reports-cited-history", bare, case)["verdict"], FAIL)
        self.assertEqual(grade("why-reports-null-results", bare, case)["verdict"], FAIL)
        self.assertEqual(grade("why-queries-evidence-categories-in-parallel", bare, case)["verdict"], FAIL)


class InterrogateSwarmArena(unittest.TestCase):
    def test_interrogate_buckets_and_models(self):
        case = load_case("interrogate-run")
        reviewers = [{"seq": 1, "tool": "Agent", "persona": None, "model": "fable", "prompt_head": "You are an adversarial code reviewer. Reviewer A"},
                     {"seq": 2, "tool": "Agent", "persona": None, "model": "opus", "prompt_head": "You are an adversarial code reviewer. Reviewer B"}]
        events = [{"seq": 1, "kind": "tool_call", "name": "Agent", "input": {}}, {"seq": 2, "kind": "tool_call", "name": "Agent", "input": {}}]
        reply = "## Verdict\n### Act On\n- bug\n### Consider\n- x\n### Noted\n- y\n### Dismissed\n- z: nit"
        trace = minimal(events=events, spawns=reviewers, final_reply=reply)
        for pid in ("interrogate-multi-reviewer-adversarial", "interrogate-reviewers-on-different-models",
                    "interrogate-sorts-four-buckets-no-auto-apply", "interrogate-read-only-when-asked"):
            with self.subTest(pid=pid):
                self.assertEqual(grade(pid, trace, case)["verdict"], PASS)
        same = minimal(events=events, spawns=[dict(r, model="opus", prompt_head="You are an adversarial code reviewer.") for r in reviewers], final_reply=reply)
        self.assertEqual(grade("interrogate-reviewers-on-different-models", same, case)["verdict"], FAIL)
        edited = minimal(events=events + [edit(3, "/w/relay/dedupe.py")], spawns=reviewers, final_reply=reply)
        self.assertEqual(grade("interrogate-read-only-when-asked", edited, case)["verdict"], FAIL)
        self.assertEqual(grade("interrogate-sorts-four-buckets-no-auto-apply", minimal(final_reply="Act on: fix it"), case)["verdict"], FAIL)

    def test_swarm_statuses(self):
        case = load_case("swarm-run")
        reply = "| package | status |\n|---|---|\n| ingest | PASS |\n| shape | PASS |\n| render | ISSUES |\n| publish | PASS |\nGaps: none."
        workers = [{"seq": i, "tool": "Agent", "prompt_head": f"Check packages/{p}/check.sh"} for i, p in enumerate(["ingest", "shape", "render", "publish"], 1)]
        events = [{"seq": i, "kind": "tool_call", "name": "Agent", "input": {}} for i in range(1, 5)]
        trace = minimal(events=events, spawns=workers, final_reply=reply)
        self.assertEqual(grade("swarm-fans-out-and-aggregates", trace, case)["verdict"], PASS)
        self.assertEqual(grade("swarm-workers-report-pass-issues-blocked", trace, case)["verdict"], PASS)
        self.assertEqual(grade("swarm-returns-one-report-with-gaps", trace, case)["verdict"], PASS)
        wrong = minimal(events=events, spawns=workers, final_reply=reply.replace("| render | ISSUES |", "| render | PASS |"))
        self.assertEqual(grade("swarm-workers-report-pass-issues-blocked", wrong, case)["verdict"], FAIL)
        self.assertEqual(grade("swarm-fans-out-and-aggregates", minimal(spawns=workers[:2], final_reply=reply), case)["verdict"], FAIL)
        encrypted = minimal(events=events, spawns=[dict(w, prompt_head=None, x_prompt_encrypted=True) for w in workers], final_reply=reply, harness="codex")
        self.assertEqual(grade("swarm-fans-out-and-aggregates", encrypted, case)["verdict"], INCONCLUSIVE)

    def test_arena_count_and_judge(self):
        case = load_case("arena-run")
        candidates = [{"seq": i, "tool": "Agent", "persona": "poteto-agent", "model": "opus", "prompt_head": f"Candidate {i}: write to /tmp/relay-key/candidate-{i}"} for i in range(1, 6)]
        judge = {"seq": 9, "tool": "Agent", "persona": None, "model": "fable", "prompt_head": "You are the read-only cross-judge. Score each against the rubric."}
        events = [{"seq": i, "kind": "tool_call", "name": "Agent", "input": {}} for i in range(1, 6)]
        reply = "Base: candidate 3. Grafts: the hashing from candidate 1. Verified with the import run."
        trace = minimal(events=events, spawns=candidates + [judge], final_reply=reply)
        self.assertEqual(grade("arena-candidate-count-adjustable", trace, case)["verdict"], PASS)
        self.assertEqual(grade("arena-candidates-own-worktrees", trace, case)["verdict"], PASS)
        self.assertEqual(grade("arena-fans-out-and-grafts", trace, case)["verdict"], PASS)
        self.assertEqual(grade("arena-readonly-cross-judge", trace, case)["verdict"], PASS)
        three = minimal(events=events[:3], spawns=candidates[:3] + [judge], final_reply=reply)
        self.assertEqual(grade("arena-candidate-count-adjustable", three, case)["verdict"], FAIL)
        self.assertEqual(grade("arena-lead-reads-rationales-and-base", trace, case)["verdict"], FAIL)

    def judged_by(self, lead, models, judge_model):
        candidates = [{"seq": i, "tool": "Agent", "persona": "poteto-agent", "model": m, "prompt_head": f"Candidate {i}: write to /tmp/relay-key/candidate-{i}"}
                      for i, m in enumerate(models, 1)]
        events = [{"seq": i, "kind": "tool_call", "name": "Agent", "input": {}} for i in range(1, len(models) + 1)]
        judge = {"seq": 9, "tool": "Agent", "persona": None, "model": judge_model, "prompt_head": "You are the read-only cross-judge. Score each against the rubric."}
        trace = minimal(events=events, spawns=candidates + [judge], final_reply="Base: candidate 3. Grafts: the hashing from candidate 1.")
        trace["model"] = lead
        return grade("arena-readonly-cross-judge", trace, load_case("arena-run"))

    def test_a_judge_on_another_tier_than_the_lead_passes_even_when_it_shares_a_candidate_model(self):
        result = self.judged_by("claude-opus-5-5", ["fable", "opus", "sonnet", "fable", "opus"], "fable")
        self.assertEqual(result["verdict"], PASS, result)
        codex = self.judged_by("gpt-6.1-sol", ["gpt-6.1-sol", "gpt-6.1-sol", "gpt-6-luna", "gpt-6.1-sol", "gpt-6.1-sol"], "gpt-6-luna")
        self.assertEqual(codex["verdict"], PASS, codex)

    def test_a_judge_on_the_leads_model_fails_when_the_run_used_another(self):
        result = self.judged_by("claude-opus-5-5", ["fable", "opus", "sonnet", "fable", "opus"], "opus")
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["failures"], ["judge runs on the lead's model although the run used another"])

    def test_a_judge_on_the_leads_model_passes_when_no_other_model_was_used(self):
        result = self.judged_by("gpt-5.6-sol", ["gpt-5.6-sol"] * 5, "gpt-5.6-sol")
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_judge_with_no_model_inherits_the_leads_and_fails_when_the_run_used_another(self):
        result = self.judged_by("claude-opus-5-5", ["fable", "opus", "sonnet", "fable", "opus"], None)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_grok_build_is_the_same_tier_as_grok(self):
        self.assertTrue(oracles.same_model("grok-4.7", "grok-4.7-build"))

    def test_two_reviewers_with_one_label_are_not_differentiated_arms(self):
        case = load_case("interrogate-run")
        events = [{"seq": 1, "kind": "tool_call", "name": "Agent", "input": {}}, {"seq": 2, "kind": "tool_call", "name": "Agent", "input": {}}]
        reply = "## Verdict\n### Act On\n- bug\n### Consider\n- x\n### Noted\n- y\n### Dismissed\n- z: nit"
        twins = [{"seq": i, "tool": "Agent", "persona": None, "model": "opus", "prompt_head": "You are an adversarial code reviewer. Reviewer A"} for i in (1, 2)]
        result = grade("interrogate-reviewers-on-different-models", minimal(events=events, spawns=twins, final_reply=reply), case)
        self.assertEqual(result["verdict"], FAIL, result)
        blind = grade("interrogate-reviewers-on-different-models",
                      minimal(events=events, spawns=[dict(s, model=None) for s in twins], final_reply=reply), case)
        self.assertEqual(blind["verdict"], INCONCLUSIVE, blind)
        arms = [dict(twins[0]), dict(twins[1], prompt_head="You are an adversarial code reviewer. Reviewer B")]
        paired = grade("interrogate-reviewers-on-different-models", minimal(events=events, spawns=arms, final_reply=reply), case)
        self.assertEqual(paired["verdict"], PASS, paired)


class OvernightAndDocs(unittest.TestCase):
    def test_attention_section(self):
        case = load_case("overnight-run")
        good = minimal(final_reply="Summary.\n\n## Attention\nreviewed by sonnet@high\n- row 4 lacks evidence")
        self.assertEqual(grade("show-me-your-work-review-ends-with-attention", good, case)["verdict"], PASS)
        self.assertEqual(grade("show-me-your-work-review-ends-with-attention", minimal(final_reply="All done."), case)["verdict"], FAIL)
        unmarked = minimal(final_reply="## Attention\n- a flag\n\n## Next steps\n- more")
        self.assertEqual(grade("show-me-your-work-review-ends-with-attention", unmarked, case)["verdict"], FAIL)

    def test_permission_ask_fails(self):
        case = load_case("overnight-run")
        asked = minimal(events=[{"seq": 0, "kind": "tool_call", "name": "AskUserQuestion", "input": {"question": "commit?"}}])
        self.assertEqual(grade("pre-answered-permission-not-asked", asked, case)["verdict"], FAIL)
        texted = minimal(events=[text(0, "The migration is ready. Should I commit it now?")])
        self.assertEqual(grade("pre-answered-permission-not-asked", texted, case)["verdict"], FAIL)

    def test_doc_impact_needs_turn_markers_then_author_result(self):
        case = load_case("doc-impact-run")
        self.assertEqual(grade("poteto-runs-documentation-impact-before-completion", minimal(), case)["verdict"], INCONCLUSIVE)
        marked = minimal(events=[dict(read(0, "documentation-impact/SKILL.md"), turn=0),
                                 dict(text(1, "Done. Author result: independent review required; reviewer verdict pass."), turn=0),
                                 dict(read(2, "documentation-impact/SKILL.md"), turn=1),
                                 dict(text(3, "Review mode: pass."), turn=1)],
                         spawns=[{"seq": 1, "tool": "Agent", "prompt_head": "Role: trail reviewer. Independent review of the docs.", "turn": 0}])
        marked["spawns"][0]["seq"] = 1
        self.assertEqual(grade("poteto-runs-documentation-impact-before-completion", marked, case)["verdict"], PASS)
        self.assertEqual(grade("documentation-impact-modes-invocable", marked, case)["verdict"], PASS)
        lazy = minimal(events=[dict(text(1, "Done. independent review not required."), turn=0), dict(text(3, "pass"), turn=1)])
        self.assertEqual(grade("documentation-impact-independent-review-pass-required", lazy, case)["verdict"], FAIL)


class SmallSkills(unittest.TestCase):
    def test_tdd_first(self):
        case = load_case("tdd-run")
        good = minimal(events=[edit(0, "/w/tests/test_export.py")] + bash(1, "python3 -m unittest discover -s tests", ok=False, head="FAIL: test_limit")
                       + [edit(3, "/w/rollup/export.py")] + bash(4, "python3 -m unittest discover -s tests", head="OK"))
        self.assertEqual(grade("poteto-tdd-failing-test-first", good, case)["verdict"], PASS)
        no_red = minimal(events=[edit(0, "/w/tests/test_export.py"), edit(1, "/w/rollup/export.py")] + bash(2, "python3 -m unittest", head="OK"))
        self.assertEqual(grade("poteto-tdd-failing-test-first", no_red, case)["verdict"], FAIL)

    def test_a_rerun_between_two_writes_in_one_command_does_not_cover_the_second(self):
        case = load_case("tdd-run")
        trace = minimal(events=[edit(0, "/w/tests/test_export.py")] + bash(1, "python3 -m unittest discover -s tests", ok=False, head="FAIL: test_limit")
                        + bash(3, "echo x > rollup/export.py; python3 -m unittest discover -s tests; echo y > rollup/load.py", head="OK"))
        self.assertNotEqual(grade("poteto-tdd-failing-test-first", trace, case)["verdict"], PASS)

    def review_verdict(self, line):
        case = load_case("doc-impact-run")
        trace = minimal(events=[dict(text(1, f"Done. Author result: independent review required. {line}"), turn=0),
                                dict(text(3, "Review mode run."), turn=1)],
                        spawns=[{"seq": 1, "tool": "Agent", "prompt_head": "Role: trail reviewer. Independent review of the docs.", "turn": 0}])
        return grade("documentation-impact-independent-review-pass-required", trace, case)["verdict"]

    def test_a_negation_in_an_earlier_sentence_does_not_void_a_pass(self):
        for line in ("No findings. The review passed.", "No files edited. Pass.", "There were no blockers; the review passed."):
            self.assertEqual(self.review_verdict(line), PASS, line)

    def test_a_failed_review_then_a_passed_re_review_is_a_pass(self):
        for line in ("The first review failed, then the re-review passed.", "The first review failed; the second passed.",
                     "The review did not find any issues and passed."):
            self.assertEqual(self.review_verdict(line), PASS, line)

    def test_cannot_and_failed_to_pass_are_not_a_pass(self):
        for line in ("The review cannot pass until the README changes.", "The review failed to pass.", "The reviewer was unable to pass it."):
            self.assertNotEqual(self.review_verdict(line), PASS, line)

    def test_a_negated_review_verdict_is_not_a_pass(self):
        case = load_case("doc-impact-run")
        trace = minimal(events=[dict(text(1, "Done. Author result: independent review required. The independent review has not passed."), turn=0),
                                dict(text(3, "Review mode run."), turn=1)],
                        spawns=[{"seq": 1, "tool": "Agent", "prompt_head": "Role: trail reviewer. Independent review of the docs.", "turn": 0}])
        self.assertNotEqual(grade("documentation-impact-independent-review-pass-required", trace, case)["verdict"], PASS)

    def test_ts_autoload(self):
        case = load_case("ts-autoload")
        loaded = minimal(events=[edit(0, "/w/src/cli.ts"), read(1, "typescript-best-practices/SKILL.md")])
        self.assertEqual(grade("typescript-rules-auto-load-on-ts-files", loaded, case)["verdict"], PASS)
        self.assertEqual(grade("typescript-rules-auto-load-on-ts-files", minimal(events=[edit(0, "/w/src/cli.ts")]), case)["verdict"], FAIL)
        self.assertEqual(grade("typescript-rules-auto-load-on-ts-files", minimal(exit_code=-9), case)["verdict"], INCONCLUSIVE)

    def test_technical_writing_mode_first(self):
        case = load_case("technical-writing-run")
        good = minimal(final_reply="Mode: how-to. Then sentence by sentence:\n- `Relay — a fast importer` splits two thoughts.")
        bad = minimal(final_reply="- `Relay — a fast importer` splits two thoughts.\nThis reads as a how-to.")
        self.assertEqual(grade("technical-writing-picks-mode-then-sentences", good, case)["verdict"], PASS)
        self.assertEqual(grade("technical-writing-picks-mode-then-sentences", bad, case)["verdict"], FAIL)
        self.assertEqual(grade("technical-writing-picks-mode-then-sentences", minimal(final_reply="Looks fine."), case)["verdict"], FAIL)

    def test_bro_shorter_and_plain(self):
        case = load_case("bro-run")
        trace = minimal(events=[dict(text(0, "The `retry()` loop in `retry.py` gives up after `RETRY_LIMIT` attempts, re-raising the last `Transient`."), turn=0),
                                dict(text(1, "It tries five times, then stops and reports the last error."), turn=1)],
                        final_reply="It tries five times, then stops and reports the last error.")
        self.assertEqual(grade("bro-restates-last-message", trace, case)["verdict"], PASS)
        self.assertEqual(grade("bro-restates-last-message", minimal(final_reply="x"), case)["verdict"], INCONCLUSIVE)

    def test_comment_sicko_spawn(self):
        case = load_case("no-comments-run")
        spawn = {"seq": 1, "tool": "Agent", "persona": "comment-sicko", "prompt_head": "Feed: the diff"}
        events = [{"seq": 1, "kind": "tool_call", "name": "Agent", "input": {}},
                  {"seq": 2, "kind": "tool_result", "name": "Agent", "ok": True, "output_head": "Yes... Ha ha ha... Yes!\n\nKill list:"}]
        self.assertEqual(grade("no-comments-spawns-comment-sicko", minimal(events=events, spawns=[spawn], final_reply="Offered an encoding."), case)["verdict"], PASS)
        self.assertEqual(grade("no-comments-spawns-comment-sicko", minimal(final_reply="Removed 9 comments."), case)["verdict"], FAIL)

    def test_blast_radius(self):
        case = load_case("blast-radius-run")
        good = minimal(events=bash(0, "PYTHONPATH=. python3 prove_offsets.py", head="offsets seen: [0]"),
                       final_reply="The one fact: every caller in relay/ingest.py, relay/verify.py and relay/summarize.py passes offset 0.\nProof: `PYTHONPATH=. python3 prove_offsets.py` printed `offsets seen: [0]`.")
        self.assertEqual(grade("blast-radius-finds-breakage", good, case)["verdict"], PASS)
        self.assertEqual(grade("blast-radius-proves-one-fact-by-running-code", good, case)["verdict"], PASS)
        essay = minimal(final_reply="The change to relay/cache.py looks safe to me.")
        self.assertEqual(grade("blast-radius-finds-breakage", essay, case)["verdict"], FAIL)
        self.assertEqual(grade("blast-radius-proves-one-fact-by-running-code", essay, case)["verdict"], FAIL)


def make_repo(parent, commits, files=None):
    root = Path(parent) / "project"
    root.mkdir()
    def git(*args):
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                       check=True, capture_output=True)
    git("init", "-q")
    for n in range(commits):
        for rel, body in (files or {"f.py": "x = 0\n"}).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(body + (f"# step {n}\n" if n else ""))
        git("add", "-A")
        git("commit", "-qm", f"step {n}")
    return root


def in_turn(turn, events):
    return [dict(e, turn=turn) for e in events]


class LiveFalseFails(unittest.TestCase):
    def repo(self, commits, files=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(tmp.name, commits, files)

    def test_bytecode_and_tool_caches_are_not_a_dirty_tree(self):
        case = load_case("route-investigation")
        project = self.repo(1)
        for rel in ("relay/__pycache__/cache.cpython-312.pyc", ".pytest_cache/v/cache/lastfailed", "node_modules/.cache/babel/x.json", "relay/stray.pyc"):
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text("x")
        trace = minimal(events=[read(0, "poteto-mode/playbooks/investigation.md")])
        self.assertEqual(grade("read-only-phrase-pins-investigation", trace, case, project)["verdict"], PASS)
        (project / "relay" / "cache.py").write_text("y = 1\n")
        result = grade("read-only-phrase-pins-investigation", trace, case, project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(len(oracles.View(trace, case, project).git_dirty()), 1)

    def test_read_only_turn_counts_only_its_own_commits(self):
        case = load_case("sticky-followup")
        project = self.repo(2)
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add a flag"}])
                  + in_turn(1, bash(1, "git commit -m 'feat: add flag'"))
                  + in_turn(3, [{"seq": 3, "kind": "user", "text": "new task"}, read(4, "poteto-mode/playbooks/investigation.md")]))
        result = grade("read-only-phrase-pins-investigation", minimal(events=events), case, project)
        self.assertEqual(result["verdict"], PASS, result)
        again = in_turn(0, [{"seq": 0, "kind": "user", "text": "add a flag"}]) + \
            in_turn(3, [{"seq": 3, "kind": "user", "text": "new task"}, read(4, "poteto-mode/playbooks/investigation.md")]
                    + bash(5, "git -C /w commit -am 'sneak'"))
        result = grade("read-only-phrase-pins-investigation", minimal(events=again), case, project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["1 commit(s) made in turn 3"])

    def sticky_trace(self, turn_one_read, worklist_first):
        shape = oracles.playbook_shape(worklist_first, ROOT / "skills")
        items = [{"text": shape["prose"][0], "state": "pending"}]
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add a flag"}])
                  + in_turn(1, [{"seq": 1, "kind": "user", "text": "continue"}, read(2, turn_one_read)])
                  + in_turn(2, [{"seq": 3, "kind": "user", "text": "do it"}, text(4, "pushing")])
                  + in_turn(3, [{"seq": 5, "kind": "user", "text": "new task"}]))
        return minimal(events=events, worklist=[{"seq": 2, "carrier": "update_plan", "items": items}])

    def test_continuing_a_named_playbook_is_not_a_reroute(self):
        case = load_case("sticky-followup")
        for pid in ("poteto-mode-sticky", "short-prompt-continues-in-context"):
            with self.subTest(pid=pid):
                result = grade(pid, self.sticky_trace("poteto-mode/playbooks/opening-a-pr.md", "opening-a-pr"), case)
                self.assertEqual(result["verdict"], PASS, result)

    def test_a_playbook_the_expected_one_never_names_is_a_reroute(self):
        case = load_case("sticky-followup")
        result = grade("poteto-mode-sticky", self.sticky_trace("poteto-mode/playbooks/bug-fix.md", "bug-fix"), case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("turn 1: re-routed to ['bug-fix']", result["failures"])
        fresh = grade("poteto-mode-sticky", self.sticky_trace("poteto-mode/playbooks/feature.md", "bug-fix"), case)
        self.assertEqual(fresh["verdict"], FAIL)
        self.assertEqual(fresh["failures"], ["turn 1: opened a fresh bug-fix worklist"])

    def codex_reviewers(self, names, models):
        events, spawns = [], []
        for n, (name, model) in enumerate(zip(names, models)):
            seq = 10 + n * 2
            events.append({"seq": seq, "kind": "tool_call", "name": "spawn_agent",
                           "input": {"task_name": name, "agent_type": "default", "model": model, "message": "gAAAAABqwEWX"}})
            events.append({"seq": seq + 1, "kind": "tool_call", "name": "SubAgentActivity", "input": {"kind": "started"}})
            spawns.append({"seq": seq, "tool": "spawn_agent", "persona": None, "model": model, "prompt_head": None,
                           "x_prompt_encrypted": True, "x_agent_role": "default"})
        reply = "Reviewers\n\nAct on\n- bug\n\nConsider\n\nNoted\n\nDismissed\n"
        return minimal(events=events, spawns=spawns, final_reply=reply, harness="codex")

    def test_encrypted_reviewer_spawns_are_counted(self):
        case = load_case("interrogate-run")
        trace = self.codex_reviewers(["reviewer_a", "reviewer_b", "reviewer_c"], ["gpt-6.1-sol", "gpt-6.1-sol", "gpt-6-luna"])
        result = grade("interrogate-multi-reviewer-adversarial", trace, case)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][0], "reviewer spawns: 3")
        self.assertEqual(grade("interrogate-reviewers-on-different-models", trace, case)["verdict"], PASS)
        nameless = self.codex_reviewers(["a1", "a2"], ["gpt-6.1-sol", "gpt-6-luna"])
        result = grade("interrogate-multi-reviewer-adversarial", nameless, case)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("counted by entry", " ".join(result["evidence"]))

    def test_readable_briefs_of_other_roles_are_not_reviewers(self):
        case = load_case("interrogate-run")
        spawns = [{"seq": 1, "tool": "Agent", "persona": None, "prompt_head": "Review the diff adversarially"},
                  {"seq": 3, "tool": "Agent", "persona": None, "prompt_head": "Map the repository layout"}]
        trace = minimal(spawns=spawns, final_reply="Act on\n")
        result = grade("interrogate-multi-reviewer-adversarial", trace, case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"][0], "1 reviewer(s); interrogate sends the diff to several")

    def test_heredoc_comparisons_and_fd_redirects_are_not_edits(self):
        case = load_case("interrogate-run")
        script = ("PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'\nfailures = 0\nassert failures > 0\nprint(f'{failures}')\nPY\n"
                  "python3 -m unittest 2>&1 | tail -3 >&2\ngit status 2>/dev/null > /dev/null\nls 2>&1\n")
        self.assertEqual(oracles.shell_writes(script), [])
        trace = minimal(events=bash(0, script), spawns=[], final_reply="Act on\nConsider\nNoted\nDismissed\n")
        self.assertEqual(grade("interrogate-read-only-when-asked", trace, case)["verdict"], PASS)
        self.assertEqual(oracles.shell_writes("cat > notes.txt <<'EOF'\nbody > 1\nEOF"), ["notes.txt"])
        self.assertEqual(oracles.shell_writes("echo hi >> out.log"), ["out.log"])

    ROLLUP_EXPORT = (
        "# export: format rows and write them in batches\n"
        "def format_row(row):\n"
        "    return f\"{row['id']},{row['qty']}\"\n\n\n"
        "def export(rows):\n"
        "    # read the rows\n"
        "    # do not remove: the sink needs a trailing newline on every row\n"
        "    lines = [format_row(row) + \"\\n\" for row in rows]\n"
        "    return len(lines)\n")
    ROLLUP_TEST = "from rollup.export import format_row\n\n\ndef test_row():\n    assert format_row({'id': 1, 'qty': 2}) == '1,2'\n"

    def rollup(self, comment_survives=False, test_changes=True):
        project = self.repo(2, {"rollup/export.py": self.ROLLUP_EXPORT, "tests/test_export.py": self.ROLLUP_TEST})
        export = ("def format_row(row):\n    return f\"{row['id']},{row['qty']}\\n\"\n\n\n"
                  "def export(rows):\n    lines = [format_row(row) for row in rows]\n    return len(lines)\n")
        if comment_survives:
            export = export.replace("    lines =", "    # do not remove: the sink needs a trailing newline on every row\n    lines =")
        (project / "rollup" / "export.py").write_text(export)
        if test_changes:
            (project / "tests" / "test_export.py").write_text(self.ROLLUP_TEST.replace("== '1,2'", "== '1,2\\n'"))
        return project

    def sicko_trace(self, reply):
        spawn = {"seq": 1, "tool": "spawn_subagent", "persona": "comment-sicko", "prompt_head": "scope: the diff"}
        events = [{"seq": 1, "kind": "tool_call", "name": "spawn_subagent", "input": {}},
                  {"seq": 2, "kind": "tool_result", "name": "spawn_subagent", "ok": True, "output_head": "Yes... Ha ha ha... Yes!"}]
        return minimal(events=events, spawns=[spawn], final_reply=reply, harness="grok")

    def test_constraint_comment_removed_with_an_encoding_passes(self):
        case = load_case("no-comments-run")
        reply = "Deleted 20 comment lines. `format_row` now returns the full line, including the trailing LF."
        result = grade("no-comments-spawns-comment-sicko", self.sicko_trace(reply), case, self.rollup())
        self.assertEqual(result["verdict"], PASS, result)

    def test_constraint_comment_removed_with_an_offer_passes(self):
        case = load_case("no-comments-run")
        reply = "Deleted 20 comments. The cheapest lock for the do not remove line is a byte test; no approval, so it is open."
        result = grade("no-comments-spawns-comment-sicko", self.sicko_trace(reply), case, self.rollup(test_changes=False))
        self.assertEqual(result["verdict"], PASS, result)

    def test_constraint_comment_removed_with_neither_encoding_nor_offer_fails(self):
        case = load_case("no-comments-run")
        result = grade("no-comments-spawns-comment-sicko", self.sicko_trace("Deleted 20 comments."), case, self.rollup(test_changes=False))
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("constraint comment removed without an encoding or an offer"))

    def test_constraint_comment_that_survives_fails(self):
        case = load_case("no-comments-run")
        reply = "Deleted 19 comments. Encoding offered for the constraint."
        result = grade("no-comments-spawns-comment-sicko", self.sicko_trace(reply), case, self.rollup(comment_survives=True))
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("constraint comment survived"))


class DeslopPass(unittest.TestCase):
    CLEAN_REPORT = (
        "from collections import Counter\n\n\n"
        "def count_by_team(rows, team=None):\n"
        "    if team is not None:\n"
        "        rows = [row for row in rows if row[\"team\"] == team]\n"
        "    counts = Counter(row[\"team\"] for row in rows)\n"
        "    return sorted(counts.items())\n")

    def roster(self, report=CLEAN_REPORT, restore_load=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(tmp.name) / "project"
        live.make_project(load_case("deslop-run"), project)
        (project / "roster" / "report.py").write_text(report)
        if restore_load:
            (project / "roster" / "load.py").write_text((CASES / "deslop-run" / "expected" / "roster" / "load.py").read_text())
        return project

    def grade(self, project, case=None, **trace):
        events = trace.pop("events", [read(0, "deslop/SKILL.md"), edit(1, "roster/report.py")])
        trace.setdefault("x_baseline", live.baseline(project) if project.is_dir() else None)
        return grade("deslop-cleans-code-slop", minimal(events=events, final_reply="Removed 8 lines.", **trace), case or load_case("deslop-run"), project)

    def test_a_clean_tree_with_green_tests_passes(self):
        result = self.grade(self.roster())
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("deslop skill read by the lead: True", result["evidence"][0])

    def test_a_skill_tool_load_counts_as_the_lead_reading_deslop(self):
        events = [{"seq": 0, "kind": "tool_call", "name": "Skill", "input": {"skill": "deslop"}}, edit(1, "roster/report.py")]
        result = self.grade(self.roster(), events=events)
        self.assertIn("deslop skill read by the lead: True", result["evidence"][0])

    def test_the_planted_history_itself_fails_on_every_plant(self):
        project = self.roster(report=(HISTORIES / "roster-team-filter" / "step-1" / "roster" / "report.py").read_text(), restore_load=False)
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("planted slop survived"))
        self.assertIn("'roster/load.py'", result["failures"][1])

    def test_a_surviving_shim_fails(self):
        shim = self.CLEAN_REPORT + "\n\ndef filter_rows(rows, team):\n    return count_by_team(rows, team)\n"
        result = self.grade(self.roster(report=shim))
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["planted slop survived: ['def filter_rows(']"])

    def test_a_kept_unrelated_edit_fails(self):
        result = self.grade(self.roster(restore_load=False))
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["file differs from its expected result: ['roster/load.py']"])

    def test_restoring_the_whole_file_loses_the_users_uncommitted_edit_and_fails(self):
        project = self.roster(restore_load=False)
        (project / "roster" / "load.py").write_text((FIXTURES / "roster" / "roster" / "load.py").read_text())
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["file differs from its expected result: ['roster/load.py']"])

    def test_a_run_that_never_loads_deslop_fails(self):
        result = self.grade(self.roster(), events=[edit(1, "roster/report.py")])
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["the deslop skill was never loaded"])

    def test_a_hanging_check_fails_instead_of_blocking(self):
        case = load_case("deslop-run")
        case["expect"] = dict(case["expect"], checks=[{"cmd": "python3 -c 'import time; time.sleep(30)'", "timeout_s": 1}])
        result = self.grade(self.roster(), case=case)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("timed out after 1s", result["failures"][0])

    def test_branch_work_moved_into_a_comment_fails(self):
        project = self.roster()
        main = project / "roster" / "__main__.py"
        line = '    parser.add_argument("--team", help="show only this team")\n'
        main.write_text(main.read_text().replace(line, ""))
        report = project / "roster" / "report.py"
        report.write_text(report.read_text() + "#" + line)
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(any(f.startswith("the branch's own work went missing") for f in result["failures"]), result)

    def test_an_unrelated_deleted_file_fails(self):
        project = self.roster()
        (project / "README.md").unlink()
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("files deleted: ['README.md']", result["failures"])

    def test_a_weakened_uncommitted_test_fails(self):
        project = self.roster()
        test = project / "tests" / "test_report.py"
        test.write_text(test.read_text().replace("self.assertEqual(", "self.assertTrue(True) or self.assertEqual("))
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("files outside the cleanup changed: ['tests/test_report.py']", result["failures"])

    def test_an_unrelated_edit_to_an_existing_file_fails(self):
        project = self.roster()
        readme = project / "README.md"
        readme.write_text(readme.read_text() + "\nSee also: teams.\n")
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("files outside the cleanup changed: ['README.md']", result["failures"])

    def test_an_amended_branch_commit_cannot_hide_a_new_file(self):
        project = self.roster()
        base = live.baseline(project)
        (project / "roster" / "notes.py").write_text("x = 1\n")
        git_in(project, "add", "roster/notes.py")
        git_in(project, "commit", "-q", "--amend", "--no-edit")
        result = self.grade(project, x_baseline=base)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("new files appeared: ['roster/notes.py']", result["failures"])

    def test_an_agent_commit_is_not_part_of_the_base(self):
        project = self.roster()
        (project / "roster" / "notes.py").write_text("x = 1\n")
        git_in(project, "add", "-A")
        git_in(project, "commit", "-q", "-m", "deslop")
        result = self.grade(project, x_baseline=None)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["new files appeared: ['roster/notes.py']"])

    def test_a_deleted_untouched_file_fails_without_crashing(self):
        project = self.roster()
        (project / "roster" / "load.py").unlink()
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn("file differs from its expected result: ['roster/load.py']", result["failures"])

    def test_a_cut_that_changes_behavior_fails_the_check(self):
        no_filter = "from collections import Counter\n\n\ndef count_by_team(rows, team=None):\n    return sorted(Counter(row[\"team\"] for row in rows).items())\n"
        result = self.grade(self.roster(report=no_filter))
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("check failed after the pass"), result)

    def test_a_new_file_fails(self):
        project = self.roster()
        (project / "roster" / "notes.py").write_text("x = 1\n")
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["new files appeared: ['roster/notes.py']"])

    def test_removing_the_branch_work_fails(self):
        project = self.roster()
        main = project / "roster" / "__main__.py"
        main.write_text(main.read_text().replace('    parser.add_argument("--team", help="show only this team")\n', ""))
        result = self.grade(project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertTrue(result["failures"][0].startswith("the branch's own work went missing"), result)

    def test_no_project_is_inconclusive(self):
        result = grade("deslop-cleans-code-slop", minimal(final_reply="done"), load_case("deslop-run"))
        self.assertEqual(result["verdict"], INCONCLUSIVE)

    def test_a_killed_run_with_no_edit_is_inconclusive(self):
        result = self.grade(self.roster(), events=[], exit_code=137)
        self.assertEqual(result["verdict"], INCONCLUSIVE)


def git_in(path, *args):
    subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


def add_worktree(project, name, commits):
    path = project.parent / name
    git_in(project, "worktree", "add", "-q", "-b", name, str(path))
    for n in range(commits):
        (path / f"{name}_{n}.py").write_text(f"value = {n}\n")
        git_in(path, "add", "-A")
        git_in(path, "commit", "-qm", f"{name} step {n}")
    return path


class OracleFalseVerdicts(unittest.TestCase):
    AUTH_ERROR = "Failed to authenticate: OAuth session expired and could not be refreshed"

    def repo(self, commits):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(tmp.name, commits)

    def dead_run(self, turn_exit_codes):
        events = []
        for turn in range(len(turn_exit_codes)):
            events += in_turn(turn, [{"seq": 2 * turn, "kind": "user", "text": "go"}, text(2 * turn + 1, self.AUTH_ERROR)])
        return minimal(events=events, final_reply=self.AUTH_ERROR, exit_code=turn_exit_codes[-1],
                       x_turns=[{"index": n, "exit_code": code} for n, code in enumerate(turn_exit_codes)])

    def test_a_run_that_never_started_is_inconclusive_for_every_promise(self):
        case = load_case("principle-steer-run")
        for pid in case["promises"]:
            result = grade(pid, self.dead_run([1, 1, 1]), case)
            self.assertEqual(result["verdict"], INCONCLUSIVE, pid)
            self.assertIn("never started", result["failures"][0])
            self.assertIn("Failed to authenticate", result["failures"][0])

    def test_a_failed_harvest_is_inconclusive_for_every_promise(self):
        case = load_case("principle-steer-run")
        trace = minimal(harness="hermes", final_reply="Done.", x_harvest_error="database disk image is malformed")
        for pid in case["promises"]:
            result = grade(pid, trace, case)
            self.assertEqual(result["verdict"], INCONCLUSIVE, pid)
            self.assertIn("database disk image is malformed", result["failures"][0])

    def test_a_spawn_result_is_its_own_not_a_siblings(self):
        events = [{"seq": 1, "kind": "tool_call", "name": "Agent", "id": "a", "input": {}},
                  {"seq": 2, "kind": "tool_call", "name": "Agent", "id": "b", "input": {}},
                  {"seq": 3, "kind": "tool_result", "name": "Agent", "id": "b", "ok": True, "output_head": "persona: poteto-agent"},
                  {"seq": 4, "kind": "tool_result", "name": "Agent", "id": "a", "ok": True, "output_head": "mapped the parser"}]
        spawns = [{"seq": 1, "tool": "Agent"}, {"seq": 2, "tool": "Agent"}]
        view = oracles.View(minimal(events=events, spawns=spawns), load_case("feature-run"), None)
        self.assertEqual(view.spawn_result(spawns[0]), "mapped the parser")
        self.assertEqual(view.spawn_result(spawns[1]), "persona: poteto-agent")

    def test_a_lone_spawn_keeps_its_wait_results(self):
        events = [{"seq": 1, "kind": "tool_call", "name": "spawn_agent", "id": "a", "input": {}},
                  {"seq": 2, "kind": "tool_result", "name": "spawn_agent", "id": "a", "ok": True, "output_head": "started"},
                  {"seq": 3, "kind": "tool_call", "name": "wait_agent", "id": "w", "input": {"timeout_ms": 10000}},
                  {"seq": 4, "kind": "tool_result", "name": "wait_agent", "id": "w", "ok": True, "output_head": "ha ha ha, MUST KILL"}]
        spawns = [{"seq": 1, "tool": "spawn_agent"}]
        view = oracles.View(minimal(events=events, spawns=spawns, harness="codex"), load_case("feature-run"), None)
        self.assertEqual(view.spawn_result(spawns[0]), "started\nha ha ha, MUST KILL")

    def test_a_run_with_one_clean_turn_is_not_dead(self):
        case = load_case("principle-steer-run")
        result = grade("principle-name-steers-agent", self.dead_run([0, 1, 1]), case)
        self.assertEqual(result["verdict"], FAIL)

    def test_find_exec_unexpanded_variables_and_quoted_bodies_are_not_edits(self):
        self.assertEqual(oracles.shell_writes("find relay tests -name __pycache__ -type d -exec rm -rf {} +"), [])
        self.assertEqual(oracles.shell_writes("find . -name '*.pyc' -exec rm -f {} \\;"), [])
        self.assertEqual(oracles.shell_writes('out="/tmp/r.csv"; rm -f "$out"; echo x >> "$exclude"'), [])
        self.assertEqual(oracles.shell_writes("python3 -c 'print(sum(1 for x in data if x>1))' \"$out\""), [])
        self.assertEqual(oracles.shell_writes("python3 -c 'import sys; print(len(sys.argv)>=2)'; ls"), [])
        self.assertEqual(oracles.shell_writes('echo done > "report.txt"'), ["report.txt"])
        self.assertEqual(oracles.shell_writes("rm -rf build/ && echo ok > notes.txt"), ["build/", "notes.txt"])

    def test_a_read_only_turn_that_cleans_bytecode_with_find_is_not_an_edit(self):
        case = load_case("sticky-followup")
        project = self.repo(1)
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add a flag"}])
                  + in_turn(3, [{"seq": 3, "kind": "user", "text": "new task"}, read(4, "poteto-mode/playbooks/investigation.md")]
                              + bash(5, "find relay tests -name __pycache__ -type d -exec rm -rf {} + ; git status --short", head="")))
        result = grade("read-only-phrase-pins-investigation", minimal(events=events), case, project)
        self.assertEqual(result["verdict"], PASS, result)

    def test_python_writes_name_literal_paths_through_direct_bound_and_open_forms(self):
        bound = "python3 - <<'EOF'\nimport pathlib\np=pathlib.Path(\"rollup/export.py\")\ns=p.read_text()\np.write_text(s.replace('a','b'))\nEOF"
        self.assertEqual(oracles.python_writes(bound), ["rollup/export.py"])
        direct = ("python3 - <<'EOF'\nfrom pathlib import Path\nPath('pkg/mod.py').write_text('x = 1')\n"
                  "with open('pkg/data.json', 'w') as handle:\n    handle.write('{}')\nEOF")
        self.assertEqual(oracles.python_writes(direct), ["pkg/mod.py", "pkg/data.json"])
        self.assertEqual(oracles.python_writes("python3 -c 'print(open(\"f.txt\").read())'"), [])
        self.assertEqual(oracles.python_writes("python3 -c 'from pathlib import Path; print(Path(\"a.py\").read_text())'"), [])

    def test_a_python_heredoc_write_is_a_project_edit_only_inside_the_project(self):
        case = load_case("bug-fix-run")
        project = self.repo(1)
        inside = "python3 - <<'EOF'\nimport pathlib\np=pathlib.Path(\"rollup/export.py\")\np.write_text(p.read_text())\nEOF"
        absolute_inside = f"python3 - <<'EOF'\nfrom pathlib import Path\nPath('{project}/rollup/sink.py').write_text('x')\nEOF"
        outside = "python3 - <<'EOF'\nfrom pathlib import Path\nPath('/Users/someone/else/probe.py').write_text('x')\nEOF"
        scratch = "python3 - <<'EOF'\nfrom pathlib import Path\nPath('/tmp/probe.py').write_text('x')\nEOF"
        events = bash(0, inside) + bash(2, absolute_inside) + bash(4, outside) + bash(6, scratch)
        view = oracles.View(minimal(events=events), case, project)
        self.assertEqual([e[1] for e in view.edits()], ["rollup/export.py", f"{project}/rollup/sink.py"])
        self.assertEqual([e[2] for e in view.project_edits()][:1], ["source"])

    def test_bug_fix_passes_on_a_red_test_then_a_fix_written_through_a_python_heredoc(self):
        case = load_case("bug-fix-run")
        write_test = "cat > tests/test_export.py <<'EOF'\nimport unittest\nEOF\npython3 -m unittest discover -s tests 2>&1 | tail -15"
        patch = ("git add tests && git commit -qm test && python3 - <<'EOF'\nimport pathlib\np=pathlib.Path(\"rollup/export.py\")\n"
                 "p.write_text(p.read_text().replace('a','b'))\nEOF\npython3 -m unittest discover -s tests 2>&1 | tail -3")
        trace = minimal(events=bash(7, write_test, head="AssertionError: '1,A' != '2,B'") + bash(10, patch, head="OK"))
        result = grade("bug-fix-uses-poteto-tdd-when-cheap", trace, case)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("tdd skill read: False", result["evidence"])

    def test_bug_fix_counts_only_a_red_run_after_the_test_was_written(self):
        case = load_case("bug-fix-run")
        no_red = minimal(events=[edit(1, "/w/tests/test_export.py"), edit(2, "/w/rollup/export.py")] + bash(3, "python3 -m unittest", head="OK"))
        self.assertEqual(grade("bug-fix-uses-poteto-tdd-when-cheap", no_red, case)["verdict"], INCONCLUSIVE)
        red_before_test = minimal(events=bash(0, "python3 -m unittest", ok=False, head="FAIL: test_old")
                                  + [edit(2, "/w/tests/test_export.py"), edit(3, "/w/rollup/export.py")])
        result = grade("bug-fix-uses-poteto-tdd-when-cheap", red_before_test, case)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertEqual(result["failures"], ["test written before the fix but no failing run is visible"])

    def delegate_trace(self, lead_red_run):
        spawn = {"seq": 3, "tool": "Agent", "persona": "poteto-agent", "prompt_head": "Implement and verify the duplicate-row retry fix"}
        events = [{"seq": 3, "kind": "tool_call", "name": "Agent", "input": {}}]
        if lead_red_run:
            events += bash(5, "git worktree add --detach /tmp/base && git -C /tmp/base apply tests.diff && python3 -m unittest",
                           ok=False, head="FAIL: test_retries_only_the_rejected_batch")
        events += bash(7, "python3 -m unittest", head="OK")
        return minimal(events=events, spawns=[spawn])

    def test_bug_fix_with_a_delegate_passes_on_the_leads_own_red_then_green_runs(self):
        case = load_case("bug-fix-run")
        result = grade("bug-fix-uses-poteto-tdd-when-cheap", self.delegate_trace(True), case)
        self.assertEqual(result["verdict"], PASS, result)
        silent = grade("bug-fix-uses-poteto-tdd-when-cheap", self.delegate_trace(False), case)
        self.assertEqual(silent["verdict"], INCONCLUSIVE, silent)

    def test_bug_fix_reads_a_red_run_out_of_json_wrapped_terminal_output(self):
        red = '{"output": "Preparing worktree\\nF\\n=====\\nFAIL: test_retries_only_the_rejected_batch\\n", "exit_code": 0}'
        green = '{"output": ".\\nRan 1 test in 0.001s\\n\\nOK\\n", "exit_code": 0}'
        spawn = {"seq": 3, "tool": "delegate_task", "persona": "poteto-agent", "prompt_head": "Implement and verify the duplicate-row retry fix"}
        events = ([{"seq": 3, "kind": "tool_call", "name": "delegate_task", "input": {}}]
                  + bash(5, "git apply tests.diff && python3 -m unittest; test $? -ne 0", head=red)
                  + bash(7, "python3 -m unittest", head=green))
        result = grade("bug-fix-uses-poteto-tdd-when-cheap", minimal(events=events, spawns=[spawn], harness="hermes"), load_case("bug-fix-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_bug_fix_repro_passes_when_a_poteto_agent_delegate_owns_the_edits_after_the_lead_reproduced(self):
        case = load_case("bug-fix-run")
        brief = "persona: poteto-agent\n\nPstack installed skill paths\n\nUse these local files"
        delegate = {"seq": 87, "tool": "spawn_subagent", "persona": "poteto-agent", "prompt_head": brief}
        spawn_call = {"seq": 87, "kind": "tool_call", "name": "spawn_subagent", "input": {}}
        repro = bash(51, "ROLLUP_BUSY_AFTER=2 python3 -m rollup data/orders.csv /tmp/out.csv", head="wrote")
        result = grade("bug-fix-reproduces-before-fixing", minimal(events=repro + [spawn_call], spawns=[delegate], harness="grok"), case)
        self.assertEqual(result["verdict"], PASS, result)
        late = grade("bug-fix-reproduces-before-fixing", minimal(events=[spawn_call] + bash(95, "ROLLUP_BUSY_AFTER=2 python3 -m rollup data/orders.csv /tmp/out.csv"),
                                                                 spawns=[delegate], harness="grok"), case)
        self.assertEqual(late["verdict"], INCONCLUSIVE, late)

    def test_commits_in_a_linked_worktree_count_as_commits_past_the_fixture(self):
        project = self.repo(1)
        add_worktree(project, "migrate", 2)
        asked = grade("pre-answered-permission-not-asked", minimal(), load_case("overnight-run"), project)
        self.assertEqual(asked["verdict"], PASS, asked)
        self.assertIn("commits past fixture: 2", asked["evidence"])
        read_only = minimal(events=[read(0, "poteto-mode/playbooks/investigation.md")])
        result = grade("read-only-phrase-pins-investigation", read_only, load_case("route-investigation"), project)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["2 commit(s) added past the fixture"])

    def test_files_changed_in_a_linked_worktree_count_as_changed_since_the_fixture(self):
        project = self.repo(1)
        add_worktree(project, "migrate", 2)
        view = oracles.View(minimal(), load_case("overnight-run"), project)
        self.assertEqual(view.changed_since_base(), {"migrate_0.py", "migrate_1.py"})

    def finished_in_one_turn(self, worktree):
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "im going to bed"}]
                          + bash(1, f"git -C {worktree} commit -qm 'migrate callers'")
                          + [text(3, "Migration done: zero old callers, fixtures pass, old api deleted.")])
                  + in_turn(1, [{"seq": 4, "kind": "user", "text": "/show-me-your-work catch me up"}, text(5, "Caught up.")]))
        return minimal(events=events, final_reply="Caught up.")

    def test_loop_facility_is_inconclusive_when_the_predicate_was_met_in_the_first_turn(self):
        project = self.repo(1)
        worktree = add_worktree(project, "migrate", 3)
        result = grade("autonomous-run-uses-loop-facility", self.finished_in_one_turn(worktree), load_case("overnight-run"), project)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertEqual(result["failures"], ["the run met its finish condition inside the first turn and never needed a wake"])

    def test_loop_facility_still_fails_a_run_that_did_nothing(self):
        project = self.repo(1)
        quiet = minimal(events=in_turn(0, [{"seq": 0, "kind": "user", "text": "go"}, text(1, "Looked around.")])
                        + in_turn(1, [{"seq": 2, "kind": "user", "text": "catch me up"}, text(3, "Nothing yet.")]))
        result = grade("autonomous-run-uses-loop-facility", quiet, load_case("overnight-run"), project)
        self.assertEqual(result["verdict"], FAIL, result)

    def trail_trace(self, followup_name, followup_target):
        spawn_input = {"task_name": "final_review", "agent_type": "poteto-agent", "model": "gpt-6-astra", "message": "gAAAAABqwEsK"}
        events = (in_turn(0, [{"seq": 10, "kind": "tool_call", "name": "spawn_agent", "input": spawn_input},
                              {"seq": 11, "kind": "tool_call", "name": "spawn_agent", "input": dict(spawn_input, task_name="parser_map", agent_type="default")}])
                  + in_turn(1, [{"seq": 30, "kind": "tool_call", "name": followup_name, "input": {"target": followup_target, "message": "gAAAAABqwEwX"}}]))
        spawns = [{"seq": 10, "turn": 0, "tool": "spawn_agent", "persona": "poteto-agent", "model": "gpt-6-astra", "prompt_head": None,
                   "x_prompt_encrypted": True, "x_child_first_reply": "persona: poteto-agent\nI will review the migration and the decision trail."},
                  {"seq": 11, "turn": 0, "tool": "spawn_agent", "persona": None, "model": "gpt-6.1-sol", "prompt_head": None,
                   "x_prompt_encrypted": True, "x_child_first_reply": "I am mapping the parser."}]
        return minimal(events=events, spawns=spawns, harness="codex", final_reply="Summary.\n\nAttention\nreviewed by gpt-6-astra@high")

    def test_a_followup_to_a_review_thread_is_the_trail_reviewer_engagement(self):
        case = load_case("overnight-run")
        for tool in ("followup_task", "send_message"):
            result = grade("show-me-your-work-spawns-trail-reviewer", self.trail_trace(tool, "final_review"), case)
            self.assertEqual(result["verdict"], PASS, (tool, result))
        rooted = grade("show-me-your-work-spawns-trail-reviewer", self.trail_trace("followup_task", "/root/final_review"), case)
        self.assertEqual(rooted["verdict"], PASS, rooted)

    def test_a_followup_to_a_non_review_thread_is_not_the_trail_reviewer_engagement(self):
        result = grade("show-me-your-work-spawns-trail-reviewer", self.trail_trace("followup_task", "parser_map"), load_case("overnight-run"))
        self.assertEqual(result["verdict"], FAIL)

    GROK_PROMPTS = ["/poteto-mode add a --json flag.", "continue", "/poteto-mode do it", "/poteto-mode new task. figure out why the cache survives."]

    def grok_lead(self, records):
        chat = ("\n".join(json.dumps(r) for r in records) + "\n").encode()
        return grok.parse_session(chat, "/w", "poteto-mode", lead=True, prompts=self.GROK_PROMPTS)

    def compacted_records(self, user_extra=None):
        query = "<user_query>\n/poteto-mode new task. figure out why the cache survives.\n</user_query>"
        return [
            {"type": "system", "content": "You are Grok."},
            {"type": "user", "synthetic_reason": "compaction_meta", "content": [{"type": "text", "text": "Summary of the earlier session."}]},
            dict({"type": "user", "content": [{"type": "text", "text": query}]}, **(user_extra or {})),
            {"type": "assistant", "model_id": "grok-4.7", "content": "I will open the investigation playbook.",
             "tool_calls": [{"id": "c1", "name": "read_file", "arguments": json.dumps({"target_file": "/w/.agents/skills/poteto-mode/playbooks/investigation.md"})}]},
            {"type": "tool_result", "tool_call_id": "c1", "content": "playbook text"},
            {"type": "assistant", "model_id": "grok-4.7", "content": "Nothing was edited."},
        ]

    def test_grok_events_after_a_resumed_turn_carry_that_turns_stamp_when_earlier_records_are_gone(self):
        lead = self.grok_lead(self.compacted_records())
        self.assertEqual([e["turn"] for e in lead["events"]], [3, 3, 3, 3, 3])
        self.assertEqual(lead["events"][0]["kind"], "user")
        self.assertEqual(lead["events"][0]["text"], "/poteto-mode new task. figure out why the cache survives.")

    def test_grok_prompt_index_wins_over_prompt_text(self):
        lead = self.grok_lead(self.compacted_records({"prompt_index": 2}))
        self.assertEqual({e["turn"] for e in lead["events"]}, {2})

    def test_grok_unmatched_prompt_follows_the_previous_turn(self):
        records = self.compacted_records()
        records.insert(3, {"type": "user", "content": [{"type": "text", "text": "<user_query>\nsomething else entirely\n</user_query>"}]})
        lead = self.grok_lead(records)
        self.assertEqual([e["turn"] for e in lead["events"] if e["kind"] == "user"], [3, 4])

    def test_grok_turns_with_no_events_in_the_lead_history_are_named(self):
        lead = self.grok_lead(self.compacted_records())
        self.assertEqual(grok.turns_without_events(lead["events"], 4), [0, 1, 2])

    def test_sticky_is_inconclusive_for_turns_whose_events_the_history_lost(self):
        case = load_case("sticky-followup")
        events = in_turn(3, [{"seq": 0, "kind": "user", "text": "new task"}, read(1, "poteto-mode/playbooks/investigation.md")])
        trace = minimal(events=events, harness="grok", x_turns_without_events=[0, 1, 2])
        for pid in ("poteto-mode-sticky", "short-prompt-continues-in-context"):
            result = grade(pid, trace, case)
            self.assertEqual(result["verdict"], INCONCLUSIVE, (pid, result))
            self.assertIn("[1, 2]", result["failures"][0])
        self.assertEqual(grade("poteto-mode-sticky", minimal(events=events, harness="grok"), case)["verdict"], FAIL)


def skill_call(seq, name, ok=True, args=""):
    return [{"seq": seq, "kind": "tool_call", "name": "Skill", "input": {"skill": name, "args": args}, "id": f"s{seq}"},
            {"seq": seq + 1, "kind": "tool_result", "name": "Skill", "ok": ok, "output_head": f"Launching skill: {name}", "id": f"s{seq}"}]


class SkillToolLoads(unittest.TestCase):
    def test_skill_tool_loads_order_why_then_how(self):
        trace = minimal(events=skill_call(1, "why", args="why is the retry limit five?") + bash(3, "git log")
                        + [text(11, "I've finished the why part. Next I'm loading the how skill.")] + skill_call(12, "how"),
                        final_reply="Why: five covers the rebuild. How: ingest calls retry().")
        result = grade("why-then-how-composition", trace, load_case("why-then-how-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"], ["first how evidence at seq 12", "first why evidence at seq 1"])

    def test_a_narrow_why_skill_load_is_teach_evidence(self):
        trace = minimal(events=skill_call(9, "why", args="Narrow scope: why did commit 23aa153 change this?") + bash(11, "git show 23aa153"),
                        final_reply="```mermaid\ngraph LR\na-->b\n```")
        result = grade("poteto-teach-runs-how-and-why", trace, load_case("teach-run"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("why evidence at seq 9", result["evidence"])

    def test_a_refused_skill_load_is_not_a_read(self):
        trace = minimal(events=skill_call(1, "why", ok=False) + skill_call(12, "how"), final_reply="done")
        result = grade("why-then-how-composition", trace, load_case("why-then-how-run"))
        self.assertEqual(result["verdict"], FAIL, result)


def codex_spawn(seq, task, reply, model="gpt-6.1-sol"):
    events = [{"seq": seq, "kind": "tool_call", "name": "spawn_agent", "input": {"task_name": task, "model": model, "message": "gAAAAABqwbhN"}},
              {"seq": seq + 1, "kind": "tool_call", "name": "SubAgentActivity", "input": {"kind": "started", "agent_path": f"/root/{task}"}},
              {"seq": seq + 2, "kind": "tool_result", "name": "spawn_agent", "ok": True, "output_head": f"{{\"task_name\":\"/root/{task}\"}}"}]
    spawn = {"seq": seq, "tool": "spawn_agent", "model": model, "prompt_head": None, "x_prompt_encrypted": True, "x_child_first_reply": reply}
    return events, spawn


def delegate(seq, head, reply=""):
    return {"seq": seq, "tool": "delegate_task", "prompt_head": head, "x_child_first_reply": reply}


class SpawnIdentity(unittest.TestCase):
    def test_codex_investigators_are_named_by_their_first_reply(self):
        events, spawns = [], []
        for seq, task, reply in ((29, "retry_history", "### Source\n\nSource control and tracked repository files. Read-only."),
                                 (32, "retry_issues", "### Source\n\nIssue / ticket tracker through GitHub MCP, read-only."),
                                 (35, "retry_docs", "### Source\n\nLong-form documents through Pages MCP. Read-only."),
                                 (59, "retry_synthesis", "Five was chosen to cover the partner mirror's nightly rebuild.\n\n[Direct] Commit 401725e")):
            more, spawn = codex_spawn(seq, task, reply)
            events += more
            spawns.append(spawn)
        events.insert(9, {"seq": 40, "kind": "tool_call", "name": "wait_agent", "input": {}})
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns, harness="codex"), load_case("why-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][:2], ["investigator spawns: 3", "one message: True"])

    def test_a_hyphenated_source_control_investigator_counts_and_the_synthesizer_does_not(self):
        spawns = [delegate(55, "Investigate source-control evidence for why the retry limit was raised to five."),
                  delegate(67, "Synthesize a confidence-calibrated answer from the supplied investigation.")]
        events = [{"seq": 55, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(60, "The history is in."),
                  {"seq": 67, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns, harness="hermes"), load_case("why-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")

    def test_a_synthesizer_that_names_investigators_is_not_one(self):
        spawns = [{"seq": 60, "tool": "spawn_subagent", "prompt_head": "You are investigating the historical context and motivation behind a piece of code. "
                   "A separate synthesizer combines your findings with other investigators' into a final answer."},
                  {"seq": 68, "tool": "spawn_subagent", "prompt_head": "You are answering a \"why\" question about a piece of code by synthesizing findings from investigators."}]
        events = [{"seq": 60, "kind": "tool_call", "name": "spawn_subagent", "input": {}}, text(66, "The source-control search is in."),
                  {"seq": 68, "kind": "tool_call", "name": "spawn_subagent", "input": {}}]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns, harness="grok"), load_case("why-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")

    def test_architecture_is_not_architect_and_the_cross_judge_is_not_a_runner(self):
        spawns = [delegate(89, "Investigate source-control and in-repo rationale for the current import architecture. Read-only."),
                  *[delegate(107, f"Produce caller-first candidate {c}: a deep import architecture. Read-only: do not edit files.") for c in "ABC"],
                  delegate(123, "Cross-judge the three import-pipeline architecture candidates against the caller-first rubric."),
                  delegate(125, "Synthesize the final caller-first import-pipeline design from the arena outcome.")]
        events = [read(80, "arena/SKILL.md"), {"seq": 89, "kind": "tool_call", "name": "delegate_task", "input": {}},
                  {"seq": 95, "kind": "tool_call", "name": "read_file", "input": {"path": "/w/relay/ingest.py"}},
                  {"seq": 107, "kind": "tool_call", "name": "delegate_task", "input": {}},
                  {"seq": 110, "kind": "tool_call", "name": "terminal", "input": {"command": "ls /tmp"}},
                  {"seq": 123, "kind": "tool_call", "name": "delegate_task", "input": {}},
                  {"seq": 125, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("architect-runs-arena-for-sketches", minimal(events=events, spawns=spawns, harness="hermes"), load_case("architect-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("runner spawns: 3", result["evidence"])

    def test_a_later_extra_runner_keeps_the_first_wave_and_the_full_brief_carries_callers(self):
        brief = "You are an architect runner (role: `architect runners`, arm {n}). READ-ONLY on the repo."
        full = brief + " ... the user said: i care most about how callers use it. Write usage first."
        calls = {n: {"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"description": f"Architect runner {n}", "prompt": full.format(n=n)}}
                 for n, seq in ((1, 21), (2, 23), (3, 25), (4, 39))}
        spawns = [{"seq": c["seq"], "tool": "Agent", "prompt_head": brief.format(n=n)} for n, c in calls.items()]
        spawns.append({"seq": 45, "tool": "Agent", "prompt_head": "You are the arena cross-judge (role: `arena cross-judge pool`). READ-ONLY. Four candidate designs are at /tmp/architect-relay."})
        events = [read(5, "arena/SKILL.md"), calls[1], calls[2], calls[3], text(27, "All three sketch runners are working in parallel."),
                  text(38, "These three differ only in policy details, so I'm spawning a fourth runner."), calls[4],
                  {"seq": 45, "kind": "tool_call", "name": "Agent", "input": {"description": "Arena cross-judge (fable)"}}]
        result = grade("architect-runs-arena-for-sketches", minimal(events=events, spawns=spawns), load_case("architect-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("briefs that lead with caller usage: 4", result["evidence"])

    def test_sequential_runners_still_fail(self):
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": "You are an architect runner. Write caller usage first."} for s in (21, 30)]
        events = [read(5, "arena/SKILL.md"), {"seq": 21, "kind": "tool_call", "name": "Agent", "input": {}}, text(25, "First one is running."),
                  {"seq": 30, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("architect-runs-arena-for-sketches", minimal(events=events, spawns=spawns), load_case("architect-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_encrypted_candidate_runners_cannot_show_caller_usage(self):
        events, spawns = [], []
        for seq, task in ((92, "candidate_one_call"), (95, "candidate_prepared"), (98, "candidate_importer")):
            more, spawn = codex_spawn(seq, task, "")
            events += more
            spawns.append(spawn)
        trace = minimal(events=[read(5, "arena/SKILL.md")] + events, spawns=spawns, harness="codex")
        result = grade("architect-runs-arena-for-sketches", trace, load_case("architect-run"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertIn("runner spawns: 3", result["evidence"])


class FanOutStructure(unittest.TestCase):
    def test_encrypted_explorers_are_known_by_a_parallel_wave_then_a_lone_spawn(self):
        events, spawns = [], []
        for seq, task, reply in ((22, "ingest_shape", "I'm tracing the CLI, ingest, and shape code."),
                                 (25, "render_publish", "I'll trace the render and publish code and report to the agent preparing the explanation."),
                                 (42, "pipeline_explanation", "bin/kiln converts a notes file into one file per tag.")):
            more, spawn = codex_spawn(seq, task, reply)
            events += more
            spawns.append(spawn)
        events[6:6] = [{"seq": 30, "kind": "tool_call", "name": "wait_agent", "input": {}}, text(38, "The CLI runs four stages.")]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="codex"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("explorers found by structure: a wave of 2 at seq 22, then a spawn at seq 42", result["evidence"])

    def test_paraphrased_explorers_in_one_delegate_call_then_a_synthesizer(self):
        spawns = [delegate(27, "Trace the complete ingest-to-publish pipeline. Return factual findings with file paths. Read-only: do not edit or write files."),
                  delegate(27, "Audit the verification evidence for the full pipeline. Do not modify anything."),
                  delegate(41, "Synthesize a direct answer stating whether the full pipeline works.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "Both reports are in."),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_readable_wave_of_judges_is_not_explorers(self):
        spawns = [delegate(27, "Read-only. You are a judge. Score the two designs against the rubric."),
                  delegate(27, "Read-only. You are a judge. Score the two designs for risk."),
                  delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "Both scores are in."),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_one_explainer_alone_is_still_no_fan_out(self):
        spawns = [{"seq": 9, "tool": "Agent", "prompt_head": "Read-only. You are writing an architectural explanation for a senior engineer."}]
        events = [{"seq": 9, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, final_reply="x"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_paraphrased_spawns_one_at_a_time_are_not_a_fan_out(self):
        spawns = [delegate(27, "Trace the ingest stage."), delegate(31, "Trace the render stage."), delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(29, "One is out."),
                  {"seq": 31, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "Both are in."),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)


class ArenaLeadReads(unittest.TestCase):
    def test_brief_named_design_notes_read_in_a_loop_and_after_the_judge_count(self):
        brief = "You're working in the relay repo. Settle the cache key format. Write `DESIGN_NOTES.md` with your reasoning."
        calls = [{"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"description": f"Cache key design {c}", "prompt": brief}}
                 for seq, c in zip((7, 9, 11, 13, 15), "ABCDE")]
        spawns = [{"seq": c["seq"], "tool": "Agent", "model": "opus", "prompt_head": brief} for c in calls]
        spawns.append({"seq": 26, "tool": "Agent", "model": "fable", "prompt_head": "READ-ONLY. You are judging five independent implementations against the rubric."})
        loop = 'W="$PWD/.claude/worktrees"; for x in a1:A a2:B a3:C a4:D; do id=${x%%:*}; cat "$W/agent-$id/DESIGN_NOTES.md"; done'
        events = (calls + bash(22, loop) + [{"seq": 26, "kind": "tool_call", "name": "Agent", "input": {}}]
                  + bash(28, 'cat "$PWD/.claude/worktrees/agent-a5/DESIGN_NOTES.md"')
                  + bash(30, 'cd "$PWD/.claude/worktrees/agent-a5"; cat relay/cache.py; cat tests/test_cache.py')
                  + [{"seq": 55, "kind": "tool_call", "name": "Write", "input": {"file_path": "/tmp/arena-cache-key/SYNTHESIS.md", "content": "x"}}])
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 5")

    def test_the_leads_own_writes_are_not_rationale_reads(self):
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": "Candidate: write rationale.md in /tmp/k/c{s}"} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = ([{"seq": s, "kind": "tool_call", "name": "Agent", "input": {}} for s in (1, 2, 3, 4, 5, 9)]
                  + [{"seq": 20, "kind": "tool_call", "name": "Write", "input": {"file_path": f"/tmp/k/c{n}/rationale.md"}} for n in range(1, 6)]
                  + bash(30, "cat > /tmp/k/rationale-summary.md <<'EOF'\nsummary\nEOF") + bash(32, "cat /tmp/k/c1/relay/cache.py"))
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 0")

    def test_encrypted_candidates_with_design_notes_read_one_by_one(self):
        events, spawns = [], []
        for seq, task in ((40, "cedar"), (43, "maple"), (46, "birch"), (80, "elm"), (103, "ash"), (140, "cross_judge")):
            more, spawn = codex_spawn(seq, task, "")
            events += more
            spawns.append(spawn)
        for n, label in enumerate(("maple", "cedar", "birch", "elm", "ash")):
            events += [{"seq": 144 + 2 * n, "kind": "tool_call", "name": "exec_command", "input": {"cmd": f"cat /tmp/relay-keys/{label}/design-notes.md"}}]
        events += [{"seq": 156, "kind": "tool_call", "name": "exec_command", "input": {"cmd": "cat /tmp/relay-keys/cedar/relay/cache.py /tmp/relay-keys/cedar/README.md"}}]
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns, harness="codex"), load_case("arena-run"))
        self.assertEqual(result["verdict"], PASS, result)


class ReplyWording(unittest.TestCase):
    def test_a_source_coverage_list_is_a_sources_section(self):
        reply = ("The caller adjustment was omitted in 3f2a1c9.\n\nSource coverage:\n\n- Git: reviewed all four commits, diffs, blame.\n"
                 "- Issues: repository identity is unavailable.\n- Team chat: no matching tool available.")
        result = grade("how-why-reports-name-sources-searched", minimal(final_reply=reply), load_case("how-then-why-run"))
        self.assertEqual(result["verdict"], PASS, result)
        bare = grade("how-why-reports-name-sources-searched", minimal(final_reply="The source of the bug is in git commit 3f2a1c9."), load_case("how-then-why-run"))
        self.assertEqual(bare["verdict"], FAIL, bare)

    def arena(self, reply):
        candidates = [{"seq": 43, "tool": "delegate_task", "prompt_head": f"Design one candidate {n}. Write under /tmp/k/candidate-{n}/"} for n in range(1, 6)]
        judge = {"seq": 49, "tool": "delegate_task", "prompt_head": "Independently cross-judge all five candidates. Read-only."}
        events = [{"seq": 43, "kind": "tool_call", "name": "delegate_task", "input": {}}, {"seq": 49, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        return grade("arena-fans-out-and-grafts", minimal(events=events, spawns=candidates + [judge], final_reply=reply, harness="hermes"), load_case("arena-run"))

    def test_a_selected_candidate_with_grafts_names_the_base(self):
        result = self.arena("Arena result\n- Candidate 1 was selected, with strict type validation grafted from candidate 2.\n- Verified: 8 unit tests passed.")
        self.assertEqual(result["verdict"], PASS, result)

    def test_an_earlier_negation_in_the_sentence_does_not_cancel_a_pick(self):
        for line in ("Candidate 2 was not selected, but candidate 1 was selected, with retries grafted from candidate 3.",
                     "We did not hesitate; candidate 1 was selected, with retries grafted from candidate 3.",
                     "Neither run converged; candidate 1 was selected anyway, with retries grafted from candidate 3."):
            result = self.arena(f"Arena result\n- {line}\n- Verified: 8 unit tests passed.")
            self.assertEqual(result["verdict"], PASS, (line, result))

    def test_a_coordinated_negation_is_not_a_pick(self):
        for line in ("Neither candidate 1 nor candidate 2 was selected, and no graft was applied.",
                     "It was not the case that candidate 1 was selected, and no graft was applied."):
            result = self.arena(f"Arena result\n- {line}\n- Verified: 8 unit tests passed.")
            self.assertEqual(result["verdict"], FAIL, (line, result))

    def test_a_negation_before_and_does_not_cancel_the_pick_after_it(self):
        result = self.arena("Arena result\n- No clear winner and candidate 1 was selected, with retries grafted from candidate 3.\n- Verified: 8 unit tests passed.")
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_negation_earlier_in_a_run_on_clause_does_not_cancel_a_pick(self):
        for line in ("I could not decide between them so candidate 1 was selected, with retries grafted from candidate 3.",
                     "Candidate 2 was not selected because it failed so candidate 1 was selected, with retries grafted from candidate 3.",
                     "The cross-judge did not agree with me so candidate 1 was selected, with retries grafted from candidate 3."):
            result = self.arena(f"Arena result\n- {line}\n- Verified: 8 unit tests passed.")
            self.assertEqual(result["verdict"], PASS, (line, result))

    def test_a_negated_selection_is_not_a_base(self):
        result = self.arena("Arena result\n- No candidate 1 was selected and no graft was applied.\n- Verified: 8 unit tests passed.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_grafts_without_a_pick_still_fail(self):
        result = self.arena("Arena result\n- Strict type validation grafted from candidate 2.\n- Verified: 8 unit tests passed.")
        self.assertEqual(result["verdict"], FAIL, result)


class ArenaWorktrees(unittest.TestCase):
    GOAL = "Design and implement one candidate for a durable cache-key format. Produce an isolated candidate artifact."

    def hermes_arena(self, setup, with_paths=True, ok=True):
        def task(n):
            where = f" Write exactly these files under /w/tmp/arena-cache-key/candidate-{n}/: cache.py, rationale.md." if with_paths else ""
            return {"goal": self.GOAL, "context": "Repository root: /w/relay. Inspect README.md and relay/cache.py." + where}
        events = bash(35, setup, ok=ok) + [{"seq": 43, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": [task(n) for n in range(1, 5)]}},
                                     {"seq": 45, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": [task(5)]}}]
        spawns = [{"seq": 43, "tool": "delegate_task", "prompt_head": self.GOAL} for _ in range(4)] + [{"seq": 45, "tool": "delegate_task", "prompt_head": self.GOAL}]
        return grade("arena-candidates-own-worktrees", minimal(events=events, spawns=spawns, harness="hermes"), load_case("arena-run"))

    def test_a_failed_mkdir_makes_no_candidate_dirs(self):
        dirs = " ".join(f"/w/tmp/arena-cache-key/candidate-{n}" for n in range(1, 6))
        result = self.hermes_arena(f"mkdir -p {dirs}", with_paths=False, ok=False)
        self.assertNotEqual(result["verdict"], PASS, result)

    def test_one_mkdir_of_five_candidate_dirs_gives_each_its_own(self):
        dirs = " ".join(f'"$TMPDIR/arena-cache-key/candidate-{n}"' for n in range(1, 6))
        result = self.hermes_arena(f'python3 -m unittest discover -s tests && mkdir -p {dirs} "$TMPDIR/arena-cache-key/judge"', with_paths=False)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("candidate directories created: 5", result["evidence"])

    def test_output_paths_past_the_prompt_head_count(self):
        result = self.hermes_arena("ls", with_paths=True)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("distinct output paths named in briefs: 5", result["evidence"])

    def test_one_shared_directory_still_fails(self):
        result = self.hermes_arena('mkdir -p "$TMPDIR/arena-cache-key/candidates"', with_paths=False)
        self.assertEqual(result["verdict"], FAIL, result)


class AuthorResultInWorkRecord(unittest.TestCase):
    def doc_turns(self, record):
        events = in_turn(0, [{"seq": 0, "kind": "user", "text": "add --json"}, read(7, "documentation-impact/SKILL.md"), record,
                             text(127, "Added --json. The docs review returned pass.")])
        events += in_turn(1, [{"seq": 130, "kind": "user", "text": "review the docs"}, read(131, "documentation-impact/SKILL.md"), text(133, "pass")])
        return minimal(events=events, harness="hermes")

    def test_an_author_result_kept_in_the_worklist_counts(self):
        todo = {"seq": 125, "kind": "tool_call", "name": "todo_list", "input": {"todos": [
            {"content": "Run documentation-impact in author mode. Author result: independent review required. Same-model trail review: pass.", "status": "completed"}]}}
        result = grade("poteto-runs-documentation-impact-before-completion", self.doc_turns(todo), load_case("doc-impact-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_an_author_record_written_by_the_lead_counts(self):
        record = {"seq": 174, "kind": "tool_call", "name": "exec_command", "input": {"cmd":
                  "python3 - <<'PY'\nrecord = {'mode': 'author', 'result': 'independent review required', 'reason': 'README changed.'}\nPY"}}
        result = grade("poteto-runs-documentation-impact-before-completion", self.doc_turns(record), load_case("doc-impact-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def review_turn(self, reply):
        todo = {"seq": 125, "kind": "tool_call", "name": "todo_list", "input": {"todos": [{"content": "Author result: independent review required."}]}}
        trace = self.doc_turns(todo)
        trace["events"] = ([e for e in trace["events"] if e.get("seq") != 127]
                           + [{"seq": 117, "turn": 0, "kind": "tool_call", "name": "delegate_task", "input": {}}, dict(text(127, reply), turn=0)])
        trace["spawns"] = [{"seq": 117, "turn": 0, "tool": "delegate_task", "prompt_head": "Run the independent review under documentation-impact review mode."}]
        return grade("documentation-impact-independent-review-pass-required", trace, load_case("doc-impact-run"))

    def test_a_review_reported_as_passed_is_a_pass_verdict(self):
        result = self.review_turn("Verification.\n- All 4 tests passed.\n- The independent documentation review passed with no findings.")
        self.assertEqual(result["verdict"], PASS, result)

    def test_passing_tests_are_not_the_reviews_verdict(self):
        result = self.review_turn("Verification.\n- All 4 tests passed.\n- The docs are updated.")
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_plan_to_get_any_required_review_is_not_an_author_result(self):
        todo = {"seq": 40, "kind": "tool_call", "name": "todo_list", "input": {"todos": [
            {"content": "Run documentation-impact in author mode and obtain any required independent review.", "status": "pending"}]}}
        result = grade("poteto-runs-documentation-impact-before-completion", self.doc_turns(todo), load_case("doc-impact-run"))
        self.assertEqual(result["verdict"], FAIL, result)


class ProjectRelativePaths(unittest.TestCase):
    def project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(tmp.name, 1, {"relay/feed.py": "x = 0\n", "README.md": "relay\n"})

    def test_a_test_file_inside_a_project_under_tmp_is_a_test(self):
        project = self.project()
        view = oracles.View(minimal(), load_case("tdd-run"), project)
        self.assertEqual(view.classify(f"{project}/tests/test_main.py"), "test")
        self.assertEqual(view.classify("/private/tmp/elsewhere/tests/test_main.py"), "scratch")

    def test_a_green_run_in_the_same_command_after_the_fix_counts(self):
        project = self.project()
        fix_and_run = "cat > rollup/__main__.py <<'EOF'\nimport argparse\nEOF\npython3 -m unittest discover -s tests -v 2>&1 | tail -8"
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main 2>&1 | tail -25", head="FAIL: test_limit_exports_only_first_n_rows\nFAILED (failures=2)")
                  + bash(13, fix_and_run, head="test_limit ... ok\nRan 3 tests\n\nOK"))
        result = grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_test_run_before_the_write_in_one_command_is_not_the_green_rerun(self):
        project = self.project()
        run_then_fix = "python3 -m unittest discover -s tests 2>&1 | tail -3; cat > rollup/__main__.py <<'EOF'\nimport argparse\nEOF"
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main", head="FAIL: test_limit\nFAILED (failures=1)")
                  + bash(13, run_then_fix, head="Ran 3 tests\n\nOK"))
        result = grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_writes_after_cd_into_a_scratch_sketch_are_not_project_edits(self):
        project = self.project()
        sketch = f"{project.parent}/tmp/arena-relay/synthesis/sketch"
        events = (bash(54, f"cd {sketch}/relay && python3 - <<'EOF'\nimport pathlib\np = pathlib.Path(\"_formats.py\"); s = p.read_text()\np.write_text(s)\nEOF")
                  + bash(56, f"cd {sketch} && sed -i '' \"s/start with a dot/not . or ../\" README.md && grep -n name README.md")
                  + bash(58, f"cd {sketch} && python3 - <<'EOF'\nimport pathlib\npathlib.Path(\"relay/summarize.py\").write_text(\"x\")\nEOF")
                  + bash(68, "git status --short && echo clean", head="clean"))
        reply = "I've stopped before implementing anything. git status is clean again. Approve the design and I'll implement it."
        result = grade("architect-checkpoint-opt-in", minimal(events=events, final_reply=reply), load_case("architect-checkpoint-run"), project)
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_project_source_edit_still_breaks_the_checkpoint(self):
        project = self.project()
        events = bash(54, f"cd {project} && sed -i '' \"s/x = 0/x = 1/\" relay/feed.py")
        result = grade("architect-checkpoint-opt-in", minimal(events=events, final_reply="Approve the design?"), load_case("architect-checkpoint-run"), project)
        self.assertEqual(result["verdict"], FAIL, result)


class SteerRevert(unittest.TestCase):
    def steer(self, keep_change):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/export.py": "start = 0\n", "tests/test_export.py": "x = 0\n"})
        if keep_change:
            (project / "rollup" / "export.py").write_text("start = 1\n")
        patch = "*** Begin Patch\n*** Update File: rollup/export.py\n@@\n-    start = 0\n*** End Patch"
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "repro first."}, edit(10, f"{project}/rollup/export.py"), text(117, "Fixed.")])
                  + in_turn(1, [{"seq": 118, "kind": "user", "text": "i said the goal is to repro. i did not ask for a fix yet."},
                                {"seq": 121, "kind": "tool_call", "name": "patch", "input": {"mode": "patch", "patch": patch}},
                                {"seq": 122, "kind": "tool_result", "name": "patch", "ok": True, "output_head": "{\"success\": true}"},
                                text(127, "I reverted the fix and regression test. The working tree is clean.")]))
        return grade("steering-prompt-redirects-run", minimal(events=events, harness="hermes"), load_case("steer-repro-run"), project)

    def test_a_revert_to_the_fixture_is_the_redirect(self):
        result = self.steer(keep_change=False)
        self.assertEqual(result["verdict"], PASS, result)

    def test_an_edit_that_leaves_source_changed_still_fails(self):
        result = self.steer(keep_change=True)
        self.assertEqual(result["verdict"], FAIL, result)


class HowWideFallbackGate(unittest.TestCase):
    def test_a_readable_wave_of_implementers_is_not_an_explorer_fan_out(self):
        spawns = [delegate(27, "Implement the CSV parser change. Edit src/parse.py and write tests."),
                  delegate(27, "Implement the exporter change. Edit src/export.py."), delegate(41, "Write the release notes.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_read_only_briefs_that_ask_for_a_fix_are_not_explorers(self):
        spawns = [delegate(27, "Read-only first, then fix the parser bug in src/parse.py."), delegate(27, "Do not modify tests. Implement the exporter change."),
                  delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_each_batched_task_needs_its_own_read_only_marker(self):
        tasks = [{"goal": "Trace the ingest stage.", "context": "Read-only: do not edit or write files."}, {"goal": "Trace the render stage.", "context": "Report what you find."}]
        spawns = [delegate(27, "Trace the ingest stage."), delegate(27, "Trace the render stage."), delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": tasks}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {"goal": "Write the answer."}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_synthesizer_that_names_explorers_is_not_one(self):
        explorers = [{"seq": 1, "tool": "Agent", "prompt_head": "You are exploring a codebase. Read-only."} for _ in range(2)]
        explorers[1] = dict(explorers[1], seq=2)
        writer = {"seq": 9, "tool": "Agent", "prompt_head": "Synthesize the two explorer reports into an architectural explanation."}
        events = [{"seq": 1, "kind": "tool_call", "name": "Agent", "input": {}}, {"seq": 2, "kind": "tool_call", "name": "Agent", "input": {}},
                  text(5, "Both are back."), {"seq": 9, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=explorers + [writer], final_reply="x"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], PASS, result)


class DesignJudgeSignal(unittest.TestCase):
    def lone_judge(self, head, events=()):
        spawn = {"seq": 5, "tool": "Agent", "prompt_head": head, "description": "review judge"}
        return minimal(events=list(events) + [{"seq": 5, "kind": "tool_call", "name": "Agent", "input": {"description": "review judge"}}],
                       spawns=[spawn], final_reply="done")

    def test_a_lone_review_judge_is_not_the_architect_fan_out(self):
        trace = self.lone_judge("You are a judge. Review this diff against the rubric: design, naming, tests.")
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", trace, load_case("feature-boundary-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_lone_review_judge_does_not_break_the_design_ladder(self):
        result = grade("design-ladder-spares-small-changes", self.lone_judge("judge: design quality"), load_case("feature-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_lone_judge_after_an_arena_load_is_not_the_fan_out(self):
        trace = self.lone_judge("Judge this diff against the rubric.", [read(1, "arena/SKILL.md")])
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", trace, load_case("feature-boundary-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_lone_judge_naming_three_sketches_is_not_the_fan_out(self):
        for head in ("You are a judge. Score the three sketches against the rubric: naming, tests.",
                     "You are a judge. Judge whether the two designs in the doc still match the rubric."):
            result = grade("poteto-mode-triggers-architect-on-boundary-crossing", self.lone_judge(head), load_case("feature-boundary-run"))
            self.assertEqual(result["verdict"], FAIL, (head, result))
            self.assertEqual(grade("design-ladder-spares-small-changes", self.lone_judge(head), load_case("feature-run"))["verdict"], PASS)

    def test_two_design_sketches_then_a_judge_are_the_fan_out(self):
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": f"Design sketch {s} for the --json output."} for s in (2, 3)]
        spawns.append({"seq": 5, "tool": "Agent", "prompt_head": "You are the cross-judge. Score the design sketches against the rubric."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {}} for s in (2, 3)] + [text(4, "Both are back."),
                  {"seq": 5, "kind": "tool_call", "name": "Agent", "input": {}}]
        trace = minimal(events=events, spawns=spawns, final_reply="done")
        self.assertEqual(grade("design-ladder-spares-small-changes", trace, load_case("feature-run"))["verdict"], FAIL)
        self.assertEqual(grade("poteto-mode-triggers-architect-on-boundary-crossing", trace, load_case("feature-boundary-run"))["verdict"], PASS)


class CandidateNeedle(unittest.TestCase):
    def test_release_candidates_are_not_design_runners(self):
        spawns = [{"seq": 5, "tool": "Agent", "prompt_head": "Check release candidate 1 build", "description": "rc1"},
                  {"seq": 6, "tool": "Agent", "prompt_head": "Check release candidate 2 build", "description": "rc2"}]
        events = [{"seq": 5, "kind": "tool_call", "name": "Agent", "input": {}}, {"seq": 6, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", minimal(events=events, spawns=spawns, final_reply="done"),
                       load_case("feature-boundary-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def codex_candidates(self, loaded):
        events, spawns = [], []
        for seq, task in ((92, "candidate_one_call"), (95, "candidate_prepared"), (98, "candidate_importer")):
            more, spawn = codex_spawn(seq, task, "")
            events += more
            spawns.append(spawn)
        reads = [read(5, f"{loaded}/SKILL.md")] if loaded else []
        return grade("architect-runs-arena-for-sketches", minimal(events=reads + events, spawns=spawns, harness="codex"), load_case("architect-run"))

    def test_candidate_task_names_count_after_architect_loads(self):
        result = self.codex_candidates("architect")
        self.assertIn("runner spawns: 3", result["evidence"])

    def test_candidate_task_names_alone_are_not_runners(self):
        result = self.codex_candidates(None)
        self.assertIn("runner spawns: 0", result["evidence"])


class SynthesizerNoun(unittest.TestCase):
    def test_a_synthesizer_named_by_noun_is_not_an_investigator(self):
        spawns = [{"seq": 10, "tool": "Agent", "prompt_head": "Source control investigator: search git history for why the retry limit is five. Read-only.",
                   "description": "git history investigator"},
                  {"seq": 20, "tool": "Agent", "prompt_head": "Role: synthesizer. Combine the investigators' reports into one answer.", "description": "synthesizer"}]
        events = [{"seq": 10, "kind": "tool_call", "name": "Agent", "input": {"description": "git history investigator"}}, text(15, "waiting"),
                  {"seq": 20, "kind": "tool_call", "name": "Agent", "input": {"description": "synthesizer"}}]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns, final_reply="x"), load_case("why-run"))
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")

    def test_a_synthesis_task_is_not_an_investigator(self):
        spawns = [{"seq": 10, "tool": "Agent", "prompt_head": "Investigate source control for the retry limit.", "task_name": "retry_history"},
                  {"seq": 20, "tool": "Agent", "prompt_head": "Write the synthesis of the git history findings.", "task_name": "retry_synthesis"}]
        events = [{"seq": 10, "kind": "tool_call", "name": "Agent", "input": {}}, text(15, "waiting"), {"seq": 20, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns, final_reply="x"), load_case("why-run"))
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")


class UntestedHunks(unittest.TestCase):
    def project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(tmp.name, 1, {"relay/feed.py": "x = 0\n", "README.md": "relay\n"})

    def test_a_source_change_in_the_tree_breaks_the_checkpoint_without_a_lead_edit(self):
        project = self.project()
        (project / "relay" / "feed.py").write_text("x = 1\n")
        spawn = {"seq": 3, "tool": "Agent", "prompt_head": "Apply the design."}
        trace = minimal(events=[{"seq": 3, "kind": "tool_call", "name": "Agent", "input": {}}], spawns=[spawn], final_reply="Approve the design?")
        result = grade("architect-checkpoint-opt-in", trace, load_case("architect-checkpoint-run"), project)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_shell_write_after_cd_out_of_the_project_is_not_a_project_edit(self):
        project = self.project()
        trace = minimal(events=bash(1, "cd /private/tmp/sketch && echo 'x = 2' > relay/feed.py"), final_reply="Read only.")
        result = grade("interrogate-read-only-when-asked", trace, load_case("interrogate-run"), project)
        self.assertEqual(result["verdict"], PASS, result)
        inside = minimal(events=bash(1, f"cd {project} && echo 'x = 2' > relay/feed.py"), final_reply="Read only.")
        self.assertEqual(grade("interrogate-read-only-when-asked", inside, load_case("interrogate-run"), project)["verdict"], FAIL)

    def test_sed_with_an_empty_backup_suffix_edits_the_named_file(self):
        project = self.project()
        trace = minimal(events=bash(1, "sed -i '' \"s/relay/Relay/\" README.md"), final_reply="Approve the design before I implement?")
        view = oracles.View(trace, load_case("architect-checkpoint-run"), project)
        self.assertEqual([e[1:] for e in view.edits()], [("README.md", "doc")])
        self.assertEqual(grade("architect-checkpoint-opt-in", trace, load_case("architect-checkpoint-run"), project)["verdict"], PASS)

    def test_a_hyphenated_source_control_spawn_is_why_evidence(self):
        spawns = [{"seq": 5, "tool": "delegate_task", "prompt_head": "Investigate source-control history for the init change."}]
        trace = minimal(events=[read(1, "how/SKILL.md"), {"seq": 5, "kind": "tool_call", "name": "delegate_task", "input": {}}],
                        spawns=spawns, final_reply="Sources consulted: git log")
        result = grade("how-then-why-sequence-honored", trace, load_case("how-then-why-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_watcher_spawn_is_a_loop_facility(self):
        spawn = {"seq": 4, "tool": "Agent", "prompt_head": "Start a watcher for the migration build."}
        trace = minimal(events=[{"seq": 4, "kind": "tool_call", "name": "Agent", "input": {}}], spawns=[spawn], final_reply="x")
        result = grade("autonomous-run-uses-loop-facility", trace, load_case("overnight-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_fixing_delegate_after_the_repro_is_a_delegated_fix(self):
        spawn = {"seq": 4, "tool": "Agent", "prompt_head": "Fixing the export retry: resume at the first unaccepted row."}
        trace = minimal(events=bash(1, "ROLLUP_BUSY_AFTER=2 python3 -m rollup data/orders.csv out.csv") + [{"seq": 4, "kind": "tool_call", "name": "Agent", "input": {}}],
                        spawns=[spawn])
        result = grade("bug-fix-reproduces-before-fixing", trace, load_case("bug-fix-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_an_independent_reviewer_spawn_is_the_docs_review(self):
        events = [dict(text(1, "Author result: independent review required."), turn=0), {"seq": 2, "turn": 0, "kind": "tool_call", "name": "Agent", "input": {}},
                  dict(text(3, "The docs review returned pass."), turn=0), dict(text(4, "pass"), turn=1)]
        spawn = {"seq": 2, "turn": 0, "tool": "Agent", "prompt_head": "You are an independent reviewer of the README change."}
        result = grade("documentation-impact-independent-review-pass-required", minimal(events=events, spawns=[spawn]), load_case("doc-impact-run"))
        self.assertEqual(result["verdict"], PASS, result)


class ArenaDistinctDirectories(unittest.TestCase):
    def arena_candidates(self, setup, sealed=False):
        spawns, events = [], []
        for n, seq in enumerate((10, 11, 12, 13, 14), 1):
            head = None if sealed else f"Candidate {n}: design the cache key. Write to /tmp/arena/shared"
            spawns.append({"seq": seq, "tool": "Agent", "prompt_head": head, "x_prompt_encrypted": sealed, "description": "cand"})
            events.append({"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"description": "cand"}})
        trace = minimal(events=bash(5, setup) + events, spawns=spawns, final_reply="x", harness="codex" if sealed else "claude-code")
        return grade("arena-candidates-own-worktrees", trace, load_case("arena-run"))

    def test_one_directory_made_five_times_is_one_directory(self):
        result = self.arena_candidates("\n".join(["mkdir -p /tmp/candidate-1"] * 5))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertIn("candidate directories created: 1", result["evidence"])

    def test_encrypted_candidates_sharing_one_directory_are_inconclusive(self):
        result = self.arena_candidates("mkdir -p /tmp/candidate-1", sealed=True)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_encrypted_candidates_with_a_directory_each_pass(self):
        made = "D=/tmp/arena; " + " && ".join(f"mkdir -p $D/candidate-{n}" for n in range(1, 6))
        result = self.arena_candidates(made, sealed=True)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIn("candidate directories created: 5", result["evidence"])

    def test_named_git_worktrees_each_count_once(self):
        added = "\n".join(f"git worktree add --detach /tmp/relay-keys/{n} HEAD" for n in ("cedar", "maple", "birch", "elm", "ash"))
        result = self.arena_candidates(added, sealed=True)
        self.assertEqual(result["verdict"], PASS, result)
        again = self.arena_candidates("\n".join(["git worktree add --detach /tmp/relay-keys/cedar HEAD"] * 5), sealed=True)
        self.assertEqual(again["verdict"], INCONCLUSIVE, again)


class WritesThroughVariables(unittest.TestCase):
    def test_a_write_through_a_shell_variable_is_not_a_rationale_read(self):
        brief = "Write `DESIGN_NOTES.md` with your reasoning."
        calls = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"description": f"cand {c}", "prompt": brief}} for s, c in zip((7, 9, 11, 13, 15), "ABCDE")]
        spawns = [{"seq": c["seq"], "tool": "Agent", "model": "opus", "prompt_head": brief} for c in calls]
        spawns.append({"seq": 26, "tool": "Agent", "model": "fable", "prompt_head": "READ-ONLY. You are judging five implementations against the rubric."})
        events = calls + [{"seq": 26, "kind": "tool_call", "name": "Agent", "input": {}}]
        for n, seq in enumerate(range(30, 40, 2)):
            events += bash(seq, f'R=/tmp/w/cand-{n}/DESIGN_NOTES.md; cat > "$R" <<EOF\nnotes\nEOF')
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events + bash(50, "cat /tmp/w/x/notes.txt"), spawns=spawns, final_reply="x"),
                       load_case("arena-run"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 0")


class ReadOnlyWave(unittest.TestCase):
    def wave(self, heads, sealed=()):
        spawns = [dict(delegate(27, h), x_prompt_encrypted=n in sealed) for n, h in enumerate(heads)] + [delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))

    def test_writers_that_spare_one_file_are_not_read_only(self):
        result = self.wave(["Add a --json flag to src/cli.py and update the parser. Do not modify the README.",
                            "Refactor src/export.py to share the formatter. Do not modify tests."])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_sparing_one_file_is_not_a_read_only_marker(self):
        result = self.wave(["Trace the ingest stage. Do not modify the README.", "Trace the render stage. Do not modify tests."])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_read_only_briefs_that_also_say_change_are_not_read_only(self):
        result = self.wave(["Read-only: do not edit or write files. Trace ingest.", "Do not modify any files. Then change the render docstring."])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_one_sealed_spawn_does_not_vouch_for_a_readable_wave(self):
        result = self.wave(["Trace the ingest stage and report.", "Trace the render stage and report."], sealed=(0,))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_wave_of_explicit_read_only_tracers_passes(self):
        result = self.wave(["Trace the ingest stage. Read-only: do not edit or write files.", "Audit the tests. Do not modify anything."])
        self.assertEqual(result["verdict"], PASS, result)


class JudgeAfterExplorers(unittest.TestCase):
    def test_explorers_then_a_design_worded_reviewer_are_not_the_fan_out(self):
        spawns = [{"seq": 5, "tool": "Agent", "prompt_head": "Explorer: trace the CLI. Read-only.", "description": "explorer 1"},
                  {"seq": 6, "tool": "Agent", "prompt_head": "Explorer: trace the store. Read-only.", "description": "explorer 2"},
                  {"seq": 20, "tool": "Agent", "prompt_head": "You are a judge. Judge whether the implementation matches the design and the rubric.", "description": "review judge"}]
        events = [{"seq": s["seq"], "kind": "tool_call", "name": "Agent", "input": {"description": s["description"]}} for s in spawns]
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", minimal(events=events, spawns=spawns, final_reply="done"), load_case("feature-boundary-run"))
        self.assertEqual(result["verdict"], FAIL, result)


class EditOrders(unittest.TestCase):
    def wave(self, contexts):
        tasks = [{"goal": "Trace one stage.", "context": c} for c in contexts]
        spawns = [delegate(27, "Trace one stage.") for _ in contexts] + [delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": tasks}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {"goal": "Write the answer."}}]
        return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))

    def test_an_edit_order_on_its_own_line_counts(self):
        result = self.wave(["Read-only: do not edit or write files.\n- Fix the parser.", "Read-only: do not edit or write files."])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_more_edit_verbs_disqualify_a_read_only_brief(self):
        for order in ("Modify src/parse.py to accept CSV.", "Rewrite src/export.py to stream.", "Patch src/export.py.",
                      "We need you to add a --json flag in src/cli.py.", "Your job is to patch src/export.py.",
                      "Replace the parser.", "Insert a guard in src/cli.py.", "Apply the diff to src/x.py.", "Append a test to tests/t.py."):
            result = self.wave(["Read-only: do not edit or write files. " + order, "Read-only: do not edit or write files. Trace the store."])
            self.assertEqual(result["verdict"], FAIL, (order, result))

    def test_tracing_briefs_still_explore(self):
        result = self.wave(["Read-only: do not edit or write files. Trace the CLI.\n- Report components.", "Do not modify anything. Audit the tests."])
        self.assertEqual(result["verdict"], PASS, result)


class ArmDirectoryResolution(unittest.TestCase):
    def arena(self, commands):
        spawns, events = [], []
        for n, seq in enumerate((10, 11, 12, 13, 14), 1):
            spawns.append({"seq": seq, "tool": "Agent", "prompt_head": f"Candidate {n}: design the cache key.", "description": "cand"})
            events.append({"seq": seq, "kind": "tool_call", "name": "Agent", "input": {"description": "cand"}})
        setup = [e for n, command in enumerate(commands) for e in bash(2 * n, command)]
        return grade("arena-candidates-own-worktrees", minimal(events=setup + events, spawns=spawns, final_reply="x"), load_case("arena-run"))

    def test_one_directory_made_in_five_commands_is_one_directory(self):
        result = self.arena(["mkdir -p /tmp/arena/candidate-1"] * 5)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_spellings_of_one_directory_are_one_directory(self):
        result = self.arena(["mkdir -p /tmp/arena/candidate-1 /tmp/arena/candidate-1/ /tmp/arena/./candidate-1 /tmp/arena/x/../candidate-1 /tmp/arena//candidate-1"])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_relative_directories_resolve_against_cd(self):
        result = self.arena([" && ".join(f"cd /tmp/{d} && mkdir -p candidate-1" for d in "abcde")])
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_variable_and_its_value_name_one_directory(self):
        result = self.arena(["D=/tmp/arena; mkdir -p $D/candidate-1 " + " ".join(f"/tmp/arena/candidate-{n}" for n in range(1, 5))])
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertIn("candidate directories created: 4", result["evidence"])

    def test_a_new_branch_name_is_not_the_worktree_path(self):
        self.assertEqual(oracles.arm_dirs("git worktree add -b cand-1 /tmp/k/cedar HEAD"), {"/tmp/k/cedar"})
        self.assertEqual(oracles.arm_dirs("git worktree add -B cand-2 /tmp/k/maple"), {"/tmp/k/maple"})


class AssignedRationaleNames(unittest.TestCase):
    def lead_reads(self, brief, reads):
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in (1, 2, 3, 4, 5, 9)]
        events += [e for n, command in enumerate(reads) for e in bash(20 + 2 * n, command)]
        return grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))

    def test_a_shared_input_the_brief_names_is_not_a_rationale(self):
        result = self.lead_reads("Read `REQUIREMENTS.md` first. Write `rationale.md` in your directory.",
                                 ["cat /tmp/k/REQUIREMENTS.md"] * 5 + ["cat /tmp/k/c1/relay/cache.py"])
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 0")

    def test_a_write_order_that_reads_an_input_first_names_only_its_output(self):
        result = self.lead_reads("Write your notes after you read `REQUIREMENTS.md`; save them to `rationale.md`.",
                                 ["cat /tmp/k/REQUIREMENTS.md"] * 5 + ["cat /tmp/k/c1/relay/cache.py"])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_an_output_file_the_brief_assigns_is_a_rationale(self):
        result = self.lead_reads("Read `REQUIREMENTS.md` first. Save your reasoning to `decision-log.md`.",
                                 [f"cat /tmp/k/c{n}/decision-log.md" for n in range(1, 6)] + ["cat /tmp/k/c1/relay/cache.py"])
        self.assertEqual(result["verdict"], PASS, result)


class HeredocRerun(unittest.TestCase):
    def test_a_green_rerun_after_a_python_heredoc_fix_counts(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/__main__.py": "x = 0\n"})
        fix = "python3 - <<'EOF'\nopen('rollup/__main__.py', 'w').write('x = 1\\n')\nEOF\npython3 -m unittest discover -s tests -v 2>&1 | tail -3"
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main", head="FAIL: test_limit\nFAILED (failures=1)")
                  + bash(13, fix, head="Ran 3 tests\n\nOK"))
        result = grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_heredoc_body_that_mentions_unittest_is_not_a_test_run(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/__main__.py": "x = 0\n"})
        fix = "python3 - <<'EOF'\nopen('rollup/__main__.py', 'w').write('x = 1\\n')\nimport unittest\nEOF"
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main", head="FAIL: test_limit\nFAILED (failures=1)")
                  + bash(13, fix, head="OK"))
        result = grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)


class ModelAliasSymmetry(unittest.TestCase):
    def test_a_short_alias_lead_and_a_full_slug_judge_are_one_model(self):
        for lead, judge in (("opus", "claude-opus-5-5"), ("claude-opus-5-5", "opus")):
            candidates = [{"seq": i, "tool": "Agent", "model": m, "prompt_head": f"Candidate {i}: write to /tmp/k/candidate-{i}"}
                          for i, m in enumerate(["fable", "sonnet", "fable"], 1)]
            judge_spawn = {"seq": 9, "tool": "Agent", "model": judge, "prompt_head": "You are the read-only cross-judge. Score each against the rubric."}
            events = [{"seq": i, "kind": "tool_call", "name": "Agent", "input": {}} for i in (1, 2, 3)]
            trace = minimal(events=events, spawns=candidates + [judge_spawn], final_reply="Base: candidate 1.")
            trace["model"] = lead
            result = grade("arena-readonly-cross-judge", trace, load_case("arena-run"))
            self.assertEqual(result["verdict"], FAIL, (lead, judge, result))


class PythonCwdPerInvocation(unittest.TestCase):
    def project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(tmp.name, 1, {"relay/feed.py": "x = 0\n"})

    def test_a_python_write_after_cd_into_an_assigned_directory_resolves_there(self):
        command = "D=/tmp/sketch; cd $D; python3 -c \"open('x.py','w').write('1')\""
        self.assertEqual(oracles.python_writes(command), ["/tmp/sketch/x.py"])

    def test_a_second_python_heredoc_writes_where_its_own_cd_points(self):
        project = self.project()
        command = (f"cd /tmp/sketch && python3 - <<'EOF'\nopen('a.py', 'w').write('x')\nEOF\n"
                   f"cd {project} && python3 - <<'EOF'\nopen('relay/feed.py', 'w').write('y')\nEOF")
        result = grade("interrogate-read-only-when-asked", minimal(events=bash(1, command), final_reply="Read only."), load_case("interrogate-run"), project)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_second_inline_python_writes_where_its_own_cd_points(self):
        project = self.project()
        command = (f"cd /tmp/sketch && python3 -c \"open('a.py','w').write('x')\"; "
                   f"cd {project} && python3 -c \"open('relay/feed.py','w').write('y')\"")
        result = grade("interrogate-read-only-when-asked", minimal(events=bash(1, command), final_reply="Read only."), load_case("interrogate-run"), project)
        self.assertEqual(result["verdict"], FAIL, result)


class PythonWritesAreNotReads(unittest.TestCase):
    def test_an_inline_python_write_is_not_a_rationale_read(self):
        brief = "Write `rationale.md` in your directory."
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in (1, 2, 3, 4, 5, 9)]
        for n in range(1, 6):
            events += bash(18 + 2 * n, f"python3 -c \"open('/tmp/c{n}/rationale.md','w').write('x')\"")
        events += bash(40, "cat /tmp/c1/relay/cache.py")
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 0")

    def test_a_read_through_a_variable_counts_once(self):
        brief = "Write `rationale.md` in your directory."
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in (1, 2, 3, 4, 5, 9)]
        for n in range(1, 4):
            events += bash(18 + 2 * n, f'R=/tmp/c{n}/rationale.md; cat "$R"')
        events += bash(40, "cat /tmp/c1/relay/cache.py")
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 3")


class SealedUnmatchedFanOut(unittest.TestCase):
    def sealed(self, seqs, texts):
        events, spawns = [], []
        for seq in seqs:
            more, spawn = codex_spawn(seq, f"task_{seq}", "")
            events += more
            spawns.append(spawn)
        for seq, body in texts:
            events.append(text(seq, body))
        events.sort(key=lambda e: e["seq"])
        return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="codex"), load_case("how-wide-run"))

    def test_one_sealed_spawn_fails(self):
        result = self.sealed([22], [])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_sealed_wave_with_no_later_spawn_fails(self):
        result = self.sealed([22, 25], [])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_sealed_spawns_sent_one_at_a_time_fail(self):
        result = self.sealed([10, 20, 30], [(15, "waiting"), (25, "waiting")])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_five_sealed_spawns_in_one_wave_fail(self):
        result = self.sealed([10, 11, 12, 13, 14, 30], [(20, "waiting")])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_a_later_sealed_wave_that_could_be_explorers_is_inconclusive(self):
        result = self.sealed([10, 20, 21, 40], [(15, "waiting"), (30, "waiting")])
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_one_readable_explainer_still_fails(self):
        spawns = [{"seq": 9, "tool": "Agent", "prompt_head": "Read-only. You are writing an architectural explanation."}]
        events = [{"seq": 9, "kind": "tool_call", "name": "Agent", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, final_reply="x"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)


class RationaleReadPaths(unittest.TestCase):
    def arena_reads(self, commands, brief="Write `design-notes.md` with your reasoning."):
        calls = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"description": f"cand {c}", "prompt": brief}} for s, c in zip((7, 9, 11, 13, 15), "ABCDE")]
        spawns = [{"seq": c["seq"], "tool": "Agent", "model": "opus", "prompt_head": brief} for c in calls]
        spawns.append({"seq": 26, "tool": "Agent", "model": "fable", "prompt_head": "READ-ONLY. You are judging five implementations against the rubric."})
        events = calls + [{"seq": 26, "kind": "tool_call", "name": "Agent", "input": {}}]
        for n, command in enumerate(commands):
            events += bash(30 + 2 * n, command)
        return grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns, final_reply="x"), load_case("arena-run"))

    def test_f1_a_write_target_inside_a_read_name_does_not_drop_the_read(self):
        result = self.arena_reads([f"cat /tmp/w/c{n}/design-notes.md > notes.md" for n in range(5)] + ["cat relay/cache.py"])
        self.assertEqual(result["verdict"], PASS, result)
        same_name = self.arena_reads([f"cat /tmp/w/c{n}/design-notes.md >> /tmp/w/design-notes.md" for n in range(5)] + ["cat relay/cache.py"])
        self.assertEqual(same_name["verdict"], PASS, same_name)

    def test_f1_an_unspaced_redirect_is_a_write_not_a_read(self):
        result = self.arena_reads([f"echo x >/tmp/w/c{n}/design-notes.md" for n in range(5)] + ["cat relay/cache.py"])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_f1_a_python_read_of_a_rationale_counts_and_its_write_does_not(self):
        reads = self.arena_reads([f"python3 -c \"print(open('/tmp/w/c{n}/design-notes.md').read())\"" for n in range(5)] + ["cat relay/cache.py"])
        self.assertEqual(reads["verdict"], PASS, reads)
        writes = self.arena_reads([f"python3 -c \"open('/tmp/w/c{n}/design-notes.md','w').write('x')\"" for n in range(5)] + ["cat relay/cache.py"])
        self.assertEqual(writes["verdict"], FAIL, writes)


class RoleEvidence(unittest.TestCase):
    def sealed(self, seq, reply, task="t", model="gpt-6.1-sol"):
        return {"seq": seq, "tool": "spawn_agent", "model": model, "prompt_head": None, "x_prompt_encrypted": True, "x_child_first_reply": reply, "task_name": task}

    def test_f3_a_first_reply_that_cites_the_architect_design_is_not_a_runner(self):
        spawns = [self.sealed(10, "I'll implement the change following the architect design."), self.sealed(10, "I'll write tests following the architect design.")]
        events = [{"seq": 10, "kind": "tool_call", "name": "spawn_agent", "input": {"task_name": "t"}}]
        result = grade("poteto-mode-triggers-architect-on-boundary-crossing", minimal(events=events, spawns=spawns, harness="codex", final_reply="done"),
                       load_case("feature-boundary-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_f7_a_candidate_that_mentions_the_rubric_is_not_a_judge(self):
        spawns = [self.sealed(10 + n, "I'll design to the rubric and score my own approach.") for n in range(5)]
        events = [{"seq": s["seq"], "kind": "tool_call", "name": "spawn_agent", "input": {"task_name": "t"}} for s in spawns]
        result = grade("arena-candidate-count-adjustable", minimal(events=events, spawns=spawns, harness="codex"), load_case("arena-run"))
        self.assertIn("candidate spawns: 5 (wanted 5)", result["evidence"])
        self.assertIn("judge spawns: 0", result["evidence"])


class StatedAuthorResult(unittest.TestCase):
    def doc_turn(self, events):
        trace_events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add --json"}] + events + [text(50, "Done.")])
                        + in_turn(1, [{"seq": 60, "kind": "user", "text": "review"}, text(61, "x")]))
        return grade("poteto-runs-documentation-impact-before-completion", minimal(events=trace_events, final_reply="x"), load_case("doc-impact-run"))

    def test_f4_a_plan_item_naming_the_phrase_is_not_an_author_result(self):
        todo = {"seq": 2, "kind": "tool_call", "name": "TodoWrite", "input": {"todos": [{"content": "Decide whether independent review required, then run it"}]}}
        result = self.doc_turn([read(1, "documentation-impact/SKILL.md"), todo])
        self.assertEqual(result["verdict"], FAIL, result)

    def test_f4_a_grep_of_the_skill_text_is_not_an_author_result(self):
        result = self.doc_turn([read(1, "documentation-impact/SKILL.md")] + bash(3, "grep -n 'independent review required' skills/documentation-impact/SKILL.md"))
        self.assertEqual(result["verdict"], FAIL, result)


class WorktreeRelativeEdits(unittest.TestCase):
    def steer(self, path_of, worktree=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/export.py": "start = 0\n", "tests/test_export.py": "x = 0\n"})
        changed = project / "rollup" / "export.py"
        if worktree:
            tree = project / ".worktrees" / "fix"
            subprocess.run(["git", "-C", str(project), "worktree", "add", "-q", "-b", "fixbranch", str(tree)], check=True, capture_output=True)
            changed = tree / "rollup" / "export.py"
        changed.write_text("start = 1\n")
        events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "repro first."}, text(117, "Fixed.")])
                  + in_turn(1, [{"seq": 118, "kind": "user", "text": "i said the goal is to repro."}, edit(121, path_of(changed)), text(127, "Reverted.")]))
        return grade("steering-prompt-redirects-run", minimal(events=events), load_case("steer-repro-run"), project)

    def test_f6_a_dot_slash_edit_that_stays_changed_still_fails(self):
        self.assertEqual(self.steer(lambda p: "./rollup/export.py")["verdict"], FAIL)
        self.assertEqual(self.steer(lambda p: "rollup//export.py")["verdict"], FAIL)

    def test_f6_a_kept_edit_in_a_worktree_inside_the_project_still_fails(self):
        self.assertEqual(self.steer(str, worktree=True)["verdict"], FAIL)


class SourcesLabel(unittest.TestCase):
    def test_f8_a_sources_label_counts_and_a_coverage_sentence_does_not(self):
        case = load_case("why-run")
        for reply, want in (("Sources coverage of the test suite is 80% and git shows nothing.", FAIL),
                            ("I searched git history. Sources: git log, README.", PASS),
                            ("The source coverage report is attached; commit 12d7ece raised it.", FAIL),
                            ("Commit 12d7ece.\n\nSource coverage:\n- Git: all commits.", PASS),
                            ("Commit 12d7ece. Sources consulted: git log.", PASS),
                            ("Commit 12d7ece.\n### Sources\n- git log", PASS)):
            self.assertEqual(grade("how-why-reports-name-sources-searched", minimal(final_reply=reply), case)["verdict"], want, reply)


class ModelTiers(unittest.TestCase):
    def judged(self, judge, lead, models):
        spawns = [{"seq": 10 + n, "tool": "Agent", "model": m, "prompt_head": "Candidate design"} for n, m in enumerate(models)]
        spawns.append({"seq": 30, "tool": "Agent", "model": judge, "prompt_head": "READ-ONLY. You are the judge scoring candidates against the rubric."})
        trace = minimal(events=[{"seq": s["seq"], "kind": "tool_call", "name": "Agent", "input": {}} for s in spawns], spawns=spawns)
        trace["model"] = lead
        return grade("arena-readonly-cross-judge", trace, load_case("arena-run"))

    def test_f9_an_unknown_lead_model_is_inconclusive(self):
        self.assertEqual(self.judged("opus", None, ["opus", "sonnet"])["verdict"], INCONCLUSIVE)

    def test_f9_another_version_of_the_leads_tier_is_the_same_tier(self):
        self.assertEqual(self.judged("claude-opus-4-1", "claude-opus-5-5", ["opus", "sonnet", "sonnet"])["verdict"], FAIL)
        self.assertEqual(self.judged("gpt-6-luna", "gpt-6.1-sol", ["gpt-6.1-sol", "gpt-6-luna"])["verdict"], PASS)


class SkillNamespaces(unittest.TestCase):
    def test_f10_a_foreign_namespace_skill_is_not_a_pstack_load(self):
        events = [{"seq": 1, "kind": "tool_call", "name": "Skill", "input": {"skill": "acme:how"}, "id": "s1"},
                  {"seq": 2, "kind": "tool_result", "name": "Skill", "ok": True, "output_head": "Launching skill: acme:how", "id": "s1"},
                  {"seq": 3, "kind": "tool_call", "name": "Skill", "input": {"skill": "pstack:why"}, "id": "s3"},
                  {"seq": 4, "kind": "tool_result", "name": "Skill", "ok": True, "output_head": "Launching skill: pstack:why", "id": "s3"}]
        view = oracles.View(minimal(events=events), load_case("why-then-how-run"), None)
        self.assertEqual(view.lead_reads(), ["why/SKILL.md"])


class SubshellWrites(unittest.TestCase):
    def test_f11_a_write_inside_a_subshell_resolves_against_its_cd(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"relay/feed.py": "x = 0\n"})
        scratch = minimal(events=bash(1, "(cd /tmp/s && echo hi > a.txt)"), final_reply="Read only.")
        self.assertEqual(grade("interrogate-read-only-when-asked", scratch, load_case("interrogate-run"), project)["verdict"], PASS)
        after = minimal(events=bash(1, "(cd /tmp/s && echo hi > a.txt); echo x > relay/feed.py"), final_reply="Read only.")
        self.assertEqual(grade("interrogate-read-only-when-asked", after, load_case("interrogate-run"), project)["verdict"], FAIL)
        self.assertEqual(oracles.python_writes("(cd /tmp/s && python3 - <<'EOF'\nopen('a.py','w').write('x')\nEOF\n)"), ["/tmp/s/a.py"])
        self.assertEqual(oracles.shell_writes("(cd /tmp/s && echo hi > a.txt)"), ["/tmp/s/a.txt"])


class CaseHygiene(unittest.TestCase):
    def words(self, text):
        return set(re.findall(r"[a-z]+", text.lower()))

    def test_no_meaning_word_in_prompts_fixtures_or_paths(self):
        banned = set(MEANINGS)
        for case_dir in sorted(CASES.iterdir()):
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            allowed = GUIDE_WORDS.get(case_dir.name, set())
            for turn in case.get("turns", []):
                with self.subTest(case=case_dir.name, turn=turn[:50]):
                    self.assertEqual(self.words(turn) & banned - allowed, set())
        for root in (FIXTURES, HISTORIES):
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                rel = str(path.relative_to(HERE))
                with self.subTest(path=rel):
                    self.assertEqual(self.words(rel) & banned, set())
                    self.assertEqual(self.words(path.read_text(encoding="utf-8", errors="replace")) & banned, set())
        for history in sorted(HISTORIES.glob("*/steps.json")):
            for step in json.loads(history.read_text(encoding="utf-8"))["steps"]:
                with self.subTest(history=history.parent.name, step=step["dir"]):
                    self.assertEqual(self.words(step["message"]) & banned, set())

    def test_no_prompt_contains_another_cases_prompt(self):
        prompts = {}
        for case_dir in sorted(CASES.iterdir()):
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            for turn in case.get("turns", []):
                bare = re.sub(r"^/[a-z-]+\s+", "", turn)
                if len(bare) >= 12:
                    prompts.setdefault(bare, set()).add(case_dir.name)
        for a, owners_a in prompts.items():
            for b, owners_b in prompts.items():
                if a != b and a in b and owners_a != owners_b and not owners_a & owners_b:
                    self.fail(f"prompt of {sorted(owners_a)} is inside the prompt of {sorted(owners_b)}: {a[:60]!r}")

    def test_every_wave_one_promise_has_an_oracle(self):
        for case_dir in sorted(CASES.iterdir()):
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            if case.get("deferred"):
                continue
            graded = install_checks() if case.get("kind") == "install" else set(oracles.ORACLES)
            for pid in case["promises"]:
                with self.subTest(case=case_dir.name, promise=pid):
                    self.assertIn(pid, graded)

    def test_every_case_fixture_and_history_exists(self):
        for case_dir in sorted(CASES.iterdir()):
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            with self.subTest(case=case_dir.name):
                self.assertTrue((FIXTURES / case["fixture"]).is_dir())
                if case.get("history"):
                    self.assertTrue((HISTORIES / case["history"] / "steps.json").is_file())
                self.assertIsInstance(case["turns"], list)
                if not case.get("deferred") and case.get("kind", "live") == "live":
                    self.assertTrue(case["turns"], "a live case needs at least one turn")

    def test_a_deferred_reason_stands_alone(self):
        tracked = set(subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n"))
        names = {Path(t).name for t in tracked}
        for case_dir in sorted(CASES.iterdir()):
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            for ref in re.findall(r"[\w./-]+\.(?:md|py|json|sh)\b", case.get("deferred") or ""):
                with self.subTest(case=case_dir.name, reference=ref):
                    self.assertTrue(ref in tracked or Path(ref).name in names, f"{case_dir.name} points at {ref}, which is not in the repository")


def install_checks():
    import install
    return {check.promise for check in install.CHECKS}


class GreenRerun(unittest.TestCase):
    def test_a_rerun_after_the_fix_counts_when_a_check_also_ran_before_it(self):
        command = "python3 -m unittest discover -s tests; echo x > rollup/export.py; python3 -m unittest discover -s tests"
        self.assertTrue(oracles.runs_after_write(command, "rollup/export.py"))

    def test_a_read_before_the_run_is_not_the_write(self):
        command = "cat rollup/export.py; python3 -m unittest discover -s tests; echo x > rollup/export.py"
        self.assertFalse(oracles.runs_after_write(command, "rollup/export.py"))


class GatedPublish(unittest.TestCase):
    PID = "opening-a-pr-gated-publish-never-bypasses"
    RUN = "no-mistakes axi run --intent-file /tmp/intent.md --no-publish-intent"

    def grade(self, *commands, final_reply="published"):
        events = []
        for n, command in enumerate(commands):
            events += bash(n * 2, command)
        return grade(self.PID, minimal(events=events, final_reply=final_reply), load_case("open-pr-gated-run"))

    def test_a_force_with_lease_push_fails_even_beside_a_gated_run(self):
        result = self.grade("git push --force-with-lease origin feat/dedupe", self.RUN)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["git push in a gated repository: git push --force-with-lease origin feat/dedupe"])

    def test_a_snapshot_push_that_also_sends_other_refs_fails(self):
        for flag in ("--follow-tags", "--tags", "--all", "--branches", "--mirror"):
            with self.subTest(flag=flag):
                result = self.grade(f"git push {flag} origin HEAD:refs/pstack/wip/feat-dedupe", self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)

    def test_a_snapshot_ref_held_in_a_variable_passes(self):
        result = self.grade("R=refs/pstack/wip/feat-dedupe; git push origin HEAD:$R", self.RUN)
        self.assertEqual(result["verdict"], PASS)

    def test_a_push_target_held_in_a_variable_fails(self):
        result = self.grade("B=feat/dedupe; git push origin $B", self.RUN)
        self.assertEqual(result["verdict"], FAIL)

    def test_a_gated_run_with_a_snapshot_push_passes(self):
        result = self.grade("git add -A && git commit -qm 'import: add --dedupe'",
                            "git push origin HEAD:refs/pstack/wip/feat-dedupe", self.RUN + " 2>&1 | tail -20")
        self.assertEqual(result["verdict"], PASS)
        self.assertEqual(result["evidence"], ["git push commands outside refs/pstack/wip/: []",
                                              "forge PR create or retarget commands: []",
                                              f"no-mistakes axi run commands that supply intent: ['{self.RUN}']",
                                              "no-mistakes axi run reattaches: []"])

    def test_every_form_of_push_to_the_push_target_fails(self):
        forms = ["git push", "git push -u origin feat/dedupe", "git -C /w/relay push origin feat/dedupe", "cd /w/relay && git push origin HEAD",
                 "GIT_TERMINAL_PROMPT=0 git push origin HEAD", "sh -c 'git push origin HEAD'", '/bin/zsh -lc "git push --force-with-lease origin HEAD"',
                 "git push origin +HEAD:refs/heads/feat/dedupe", "git push origin HEAD:refs/pstack/wip/a HEAD:main", "git push --tags origin",
                 "timeout 60 git push origin HEAD", "git status | git push origin HEAD", "git push origin feat/dedupe 2>&1 | tail -5"]
        for command in forms:
            with self.subTest(command=command):
                result = self.grade(command, self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)
                self.assertEqual(len(result["failures"]), 1)

    def test_a_push_that_the_remote_rejected_still_fails(self):
        trace = minimal(events=bash(0, "git push origin feat/dedupe", ok=False, head="rejected") + bash(2, self.RUN))
        self.assertEqual(grade(self.PID, trace, load_case("open-pr-gated-run"))["verdict"], FAIL)

    def test_snapshot_pushes_and_their_deletion_pass(self):
        for command in ("git push origin HEAD:refs/pstack/wip/feat-dedupe", "git push --force origin +HEAD:refs/pstack/wip/feat-dedupe",
                        "git push origin --delete refs/pstack/wip/feat-dedupe", "git push origin :refs/pstack/wip/feat-dedupe"):
            with self.subTest(command=command):
                self.assertEqual(self.grade(command, self.RUN)["verdict"], PASS)

    def test_text_that_only_mentions_a_push_is_not_a_push(self):
        mentions = ["git commit -qm 'never git push here'", "echo git push", "git log --oneline -3",
                    "cat > /tmp/intent.md <<'EOF'\ngit push origin main\nEOF"]
        self.assertEqual(self.grade(*mentions, self.RUN)["verdict"], PASS)

    def test_a_run_without_the_no_publish_flag_fails(self):
        result = self.grade("no-mistakes axi run --intent-file /tmp/intent.md")
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["failures"], ["axi run with intent but without --no-publish-intent: no-mistakes axi run --intent-file /tmp/intent.md"])

    def test_a_trace_that_never_publishes_is_inconclusive(self):
        for commands in ((), ("no-mistakes axi", "no-mistakes axi run --help", "git status")):
            with self.subTest(commands=commands):
                result = self.grade(*commands)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertEqual(result["failures"], ["no `no-mistakes axi run` that supplies intent, no forge PR command, and no `git push` in the trace"])

    def test_a_push_inside_a_compound_statement_fails(self):
        forms = ["for b in a b; do git push origin $b; done", "if true; then git push origin HEAD; fi", "{ git push origin HEAD; }",
                 "! git push origin HEAD", "( git push origin HEAD )", "git status && ( cd /w/relay && git push )",
                 "while read b; do (git push origin $b); done < branches", "if git push origin HEAD; then echo ok; fi",
                 "false || { echo retry; git push origin HEAD; }", "true | { git push origin HEAD; }"]
        for command in forms:
            with self.subTest(command=command):
                result = self.grade(command, self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)
                self.assertTrue(result["failures"], result)
                self.assertTrue(all(f.startswith("git push in a gated repository: git push") for f in result["failures"]), result)

    def test_a_push_fed_to_a_shell_fails(self):
        forms = ["bash <<'EOF'\nset -e\ngit push origin HEAD\nEOF", "sh -s <<EOF\nfor b in a b; do git push origin $b; done\nEOF",
                 "cd /w/relay && zsh <<'SCRIPT'\ngit push --force-with-lease origin HEAD\nSCRIPT",
                 "bash -c 'for b in a b; do git push origin $b; done'", "sh -c 'if true; then git push; fi'",
                 "bash -lc \"git status && { git push origin HEAD; }\""]
        for command in forms:
            with self.subTest(command=command):
                result = self.grade(command, self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)
                self.assertTrue(all(f.startswith("git push in a gated repository: git push") for f in result["failures"]), result)

    def test_a_push_through_xargs_or_a_substitution_fails(self):
        forms = ["echo a b | xargs git push origin", "printf 'a\\nb\\n' | xargs -n1 git push origin", "echo a | xargs -I{} git push origin {}",
                 "echo a | xargs -r -n 1 -P4 git push origin", "echo a | xargs sh -c 'git push origin $0'",
                 "echo $(git push origin HEAD)", "x=`git push origin HEAD`", 'echo "pushed: $(git push origin HEAD)"',
                 "echo $(echo $(git push origin HEAD))", "echo $(git status; git push origin HEAD)"]
        for command in forms:
            with self.subTest(command=command):
                result = self.grade(command, self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)
                self.assertEqual(len(result["failures"]), 1, result)

    def test_compound_snapshot_pushes_and_quoted_mentions_pass(self):
        commands = ["for b in a b; do git push origin HEAD:refs/pstack/wip/$b; done", "{ git push origin HEAD:refs/pstack/wip/a; }",
                    "bash <<'EOF'\ngit push origin HEAD:refs/pstack/wip/a\nEOF", "echo a | xargs -I{} git push origin HEAD:refs/pstack/wip/{}",
                    "echo '$(git push origin HEAD)'", "git commit -qm 'fix `git push` docs'", "echo then do else git status",
                    "cat > /tmp/note.sh <<'EOF'\ngit push origin HEAD\nEOF", "git branch do"]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.grade(command, self.RUN)["verdict"], PASS, command)

    def test_a_forge_pr_command_fails(self):
        forms = ["gh pr create --fill", "gh pr create --base feat/parent --title t", "gh -R acme/relay pr create", "gh pr edit 12 --base main",
                 "gh pr edit 12 -B main", "cd /w/relay && gh pr create --fill", "origin pr create --status open", "origin pr edit 12 --base main"]
        for command in forms:
            with self.subTest(command=command):
                result = self.grade(command, self.RUN)
                self.assertEqual(result["verdict"], FAIL, result)
                self.assertEqual(result["failures"], [f"forge PR command in a gated repository: {command.split(' && ')[-1]}"])

    def test_forge_commands_that_do_not_create_or_retarget_pass(self):
        for command in ("gh pr view 12 --json body", "gh pr edit 12 --body-file /tmp/body.md", "gh pr create --help", "gh pr ready 12", "gh pr checks 12"):
            with self.subTest(command=command):
                self.assertEqual(self.grade(command, self.RUN)["verdict"], PASS, command)

    def test_a_bare_reattach_is_not_a_failure(self):
        result = self.grade(self.RUN, "no-mistakes axi run")
        self.assertEqual(result["verdict"], PASS)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["evidence"][-1], "no-mistakes axi run reattaches: ['no-mistakes axi run']")

    def test_a_reattach_alone_never_published_so_is_inconclusive(self):
        result = self.grade("no-mistakes axi run")
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertEqual(result["failures"], ["no `no-mistakes axi run` that supplies intent, no forge PR command, and no `git push` in the trace"])

    def test_every_form_of_intent_needs_the_flag(self):
        for command in ("no-mistakes axi run --intent 'ship it'", "echo ship | no-mistakes axi run --intent -", "no-mistakes axi run --intent-file=/tmp/i.md",
                        "no-mistakes axi run --base-branch feat/parent --intent-file /tmp/i.md"):
            with self.subTest(command=command):
                self.assertEqual(self.grade(command)["verdict"], FAIL, command)
        flagged = "no-mistakes axi run --base-branch feat/parent --intent-file /tmp/i.md --no-publish-intent"
        self.assertEqual(self.grade(flagged)["verdict"], PASS)


class Issue133WritesAndReruns(unittest.TestCase):
    def test_n5_a_cd_inside_command_substitution_scopes_its_writes(self):
        self.assertEqual(oracles.shell_writes("x=$(cd /tmp/s && echo hi > a.txt); echo x > b.txt"), ["/tmp/s/a.txt", "b.txt"])
        self.assertEqual(oracles.shell_writes("echo $(cd /tmp/s && pwd) > where.txt"), ["where.txt"])

    def test_n5_spaced_nested_subshells_scope_their_writes(self):
        self.assertEqual(oracles.shell_writes("( (cd /tmp/s && echo hi > a.txt) ; echo x > b.txt)"), ["/tmp/s/a.txt", "b.txt"])

    def test_n7_a_redirect_on_cd_writes_in_the_directory_it_leaves(self):
        self.assertEqual(oracles.shell_writes("cd /tmp/s > moved.log && echo x > a.txt"), ["moved.log", "/tmp/s/a.txt"])

    def test_f12_scratch_and_test_names_need_a_word_boundary(self):
        view = oracles.View(minimal(), {}, None)
        names = ("verify.py", "scratch.py", "reprocess.py", "contest.py", "latest.py", "attestation.py",
                 "verify_tally_json.py", "repro-retry.sh", "scratchpad/a.py", "tests/test_x.py", "pkg/x_test.go", "__tests__/a.js")
        self.assertEqual({n: view.classify(n) for n in names},
                         {"verify.py": "source", "scratch.py": "source", "reprocess.py": "source", "contest.py": "source",
                          "latest.py": "source", "attestation.py": "source", "verify_tally_json.py": "scratch",
                          "repro-retry.sh": "scratch", "scratchpad/a.py": "scratch", "tests/test_x.py": "test",
                          "pkg/x_test.go": "test", "__tests__/a.js": "test"})

    def test_f13_copy_install_perl_dd_and_ed_write_their_targets(self):
        for command, want in (("cp a.py b.py", ["b.py"]), ("cp -r notes/a.md notes/b.md out/", ["out/"]),
                              ("install -m 644 a.py bin/a.py", ["bin/a.py"]), ("perl -pi -e 's/a/b/' x.py", ["x.py"]),
                              ("dd if=a.bin of=b.bin bs=1", ["b.bin"]), ("ed -s x.py <<'EOF'\n1d\nw\nEOF", ["x.py"]),
                              ("pip install requests", []), ("java -cp lib/a.jar Main", []), ("perl -ne 'print' x.py", [])):
            self.assertEqual(oracles.shell_writes(command), want, command)

    def test_f13_a_patch_writes_the_files_it_names(self):
        body = "--- a/rollup/export.py\n+++ b/rollup/export.py\n@@ -1 +1 @@\n-x\n+y\nEOF"
        self.assertEqual(oracles.shell_writes("git apply <<'EOF'\n" + body), ["rollup/export.py"])
        self.assertEqual(oracles.shell_writes("cat > /tmp/f.diff <<'EOF'\n" + body + "\ncd /w && patch -p1 < /tmp/f.diff"),
                         ["/tmp/f.diff", "/w/rollup/export.py"])
        self.assertEqual(oracles.shell_writes("git apply --check <<'EOF'\n" + body), [])
        self.assertEqual(oracles.shell_writes("git apply fix.patch"), [])

    def test_copilot_each_patch_writes_only_its_own_body(self):
        def body(name):
            return f"--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-x\n+y\nEOF"
        command = "cd /a && git apply <<'EOF'\n" + body("x.py") + "\ncd /b && git apply <<'EOF'\n" + body("y.py")
        self.assertEqual(oracles.shell_writes(command), ["/a/x.py", "/b/y.py"])
        saved = "cat > /tmp/x.diff <<'EOF'\n" + body("x.py") + "\ncat > /tmp/y.diff <<'EOF'\n" + body("y.py") + "\ncd /b && patch -p1 < /tmp/y.diff"
        self.assertEqual(oracles.shell_writes(saved), ["/tmp/x.diff", "/tmp/y.diff", "/b/y.py"])

    def test_f13_copies_into_rationale_paths_are_not_rationale_reads(self):
        brief = "Write `rationale.md` in your directory."
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in (1, 2, 3, 4, 5, 9)]
        for n in range(1, 6):
            events += bash(18 + 2 * n, f"cp /tmp/template.md /tmp/c{n}/rationale.md")
        events += bash(40, "cat /tmp/c1/relay/cache.py")
        result = grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 0")

    def test_copilot_a_relative_cd_out_of_the_project_is_not_a_project_edit(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/export.py": "x = 0\n"})
        def edits(command):
            return oracles.View(minimal(events=bash(1, command)), {}, project).edits()
        self.assertEqual(edits("cd ../scratch && python3 -c \"open('x.py','w').write('1')\""), [])
        self.assertEqual(edits("cd rollup && python3 -c \"open('x.py','w').write('1')\""), [(1, "rollup/x.py", "source")])
        self.assertEqual(edits("cd ../scratch && echo x > x.py"), [])
        self.assertEqual(edits("cd rollup && echo x > x.py"), [(1, "rollup/x.py", "source")])

    def test_n15_a_path_write_text_call_is_the_write(self):
        write = "python3 -c \"from pathlib import Path; Path('rollup/export.py').write_text('x')\""
        self.assertFalse(oracles.runs_after_write(f"cat rollup/export.py; python3 -m unittest; {write}", "rollup/export.py"))
        self.assertTrue(oracles.runs_after_write(f"{write}; python3 -m unittest", "rollup/export.py"))

    def test_n15_each_write_form_orders_against_the_rerun(self):
        for write in ("echo x | tee rollup/export.py", "sed -i 's/a/b/' rollup/export.py",
                      "python3 -c \"open('rollup/export.py', 'w').write('x')\"", "cp /tmp/export.py rollup/export.py"):
            self.assertTrue(oracles.runs_after_write(f"{write}; python3 -m unittest", "rollup/export.py"), write)
            self.assertFalse(oracles.runs_after_write(f"python3 -m unittest; {write}", "rollup/export.py"), write)

    def test_a_second_write_after_the_run_is_not_rerun(self):
        self.assertFalse(oracles.runs_after_write("echo a > rollup/export.py; python3 -m unittest; echo b > rollup/export.py", "rollup/export.py"))
        self.assertTrue(oracles.runs_after_write("echo a > rollup/export.py; echo b > rollup/export.py; python3 -m unittest", "rollup/export.py"))

    def test_copilot_a_write_matches_its_own_path_not_its_basename(self):
        command = "echo a > src/index.py; python3 -m unittest; echo b > lib/index.py"
        self.assertTrue(oracles.runs_after_write(command, "src/index.py"))
        self.assertFalse(oracles.runs_after_write(command, "lib/index.py"))
        self.assertTrue(oracles.runs_after_write("cd /w && echo a > src/a.py && python3 -m pytest", "/w/src/a.py"))

    def tdd(self, events):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = make_repo(tmp.name, 1, {"rollup/__main__.py": "x = 0\n"})
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main", ok=False, head="FAIL: test_limit\nFAILED (failures=1)")
                  + [{"seq": 12, "kind": "tool_call", "name": "Edit", "input": {"file_path": f"{project}/rollup/__main__.py"}}] + events)
        return grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)["verdict"]

    def test_f15_a_comment_naming_a_test_runner_is_not_a_green_rerun(self):
        self.assertEqual(self.tdd(bash(14, "git status --short  # rerun unittest next", head="Looks ok")), INCONCLUSIVE)
        self.assertEqual(self.tdd(bash(14, "python3 -m unittest -v tests.test_main", head="test_limit (tests.test_main.T) ... ok")), PASS)

    def test_f15_a_comment_is_not_a_delegates_green_run(self):
        spawn = {"seq": 3, "tool": "Agent", "persona": "poteto-agent", "prompt_head": "Implement the retry fix"}
        events = ([{"seq": 3, "kind": "tool_call", "name": "Agent", "input": {}}]
                  + bash(5, "python3 -m unittest", ok=False, head="FAIL: test_retry")
                  + bash(7, "git log --oneline -1  # unittest is green in the delegate", head="ok"))
        result = grade("bug-fix-uses-poteto-tdd-when-cheap", minimal(events=events, spawns=[spawn]), load_case("bug-fix-run"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_copilot_the_rerun_must_follow_the_latest_source_edit(self):
        green = bash(14, "python3 -m unittest tests.test_main", head="Ran 1 test\n\nOK")
        self.assertEqual(self.tdd(green), PASS)
        self.assertEqual(self.tdd(green + [{"seq": 16, "kind": "tool_call", "name": "Edit", "input": {"file_path": "rollup/__main__.py"}}]), INCONCLUSIVE)

    def test_a_dir_the_command_made_and_removed_is_not_a_source_edit(self):
        smoke = "T=./.smoke; mkdir -p $T; python3 -m rollup data/orders.csv $T/a.csv; rm -rf $T; git status --short"
        self.assertEqual(oracles.shell_writes(smoke), [])
        self.assertEqual(oracles.shell_writes("rm -rf build; mkdir -p build"), ["build"])
        green = bash(14, "python3 -m unittest discover -s tests -v 2>&1 | tail -8", head="Ran 3 tests in 0.004s\n\nOK")
        self.assertEqual(self.tdd(green + bash(20, smoke, head=" M rollup/__main__.py")), PASS)

    def test_an_artifact_run_later_in_the_writing_command_proves_it_works(self):
        case = load_case("bug-fix-run")
        restore = "cp /tmp/final/export.py rollup/export.py"
        run = "python3 -m rollup data/orders.csv /tmp/out.csv"
        self.assertEqual(grade("prove-it-works-checks-real-artifact", minimal(events=bash(5, f"{restore}\n{run}")), case)["verdict"], PASS)
        self.assertEqual(grade("prove-it-works-checks-real-artifact", minimal(events=bash(5, f"{run}\n{restore}"), final_reply="done"), case)["verdict"], FAIL)

    def author_turn(self, *events, pid="poteto-runs-documentation-impact-before-completion"):
        trace_events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add --json"}, read(1, "documentation-impact/SKILL.md"), *events, text(50, "Done.")])
                        + in_turn(1, [{"seq": 60, "kind": "user", "text": "review"}, text(61, "x")]))
        return grade(pid, minimal(events=trace_events, final_reply="x"), load_case("doc-impact-run"))

    def test_n3_a_labeled_result_in_pending_work_is_not_an_author_result(self):
        label = "Result: independent review required"
        pending = {"seq": 2, "kind": "tool_call", "name": "TodoWrite", "input": {"todos": [{"content": f"Record {label}", "status": "pending"}]}}
        plan = {"seq": 2, "kind": "tool_call", "name": "update_plan", "input": {"plan": [{"step": f"Record {label}", "status": "pending"}]}}
        brief = {"seq": 2, "kind": "tool_call", "name": "Agent", "input": {"prompt": f"Review the docs. Report `{label}` or `Result: independent review not required`."}}
        done = {"seq": 2, "kind": "tool_call", "name": "TodoWrite", "input": {"todos": [{"content": f"Record {label}", "status": "completed"}]}}
        handoff = {"seq": 2, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": [{"context": "Author result: `independent review required` because the README changed."}]}}
        self.assertEqual(self.author_turn(pending)["verdict"], FAIL)
        self.assertEqual(self.author_turn(plan)["verdict"], FAIL)
        self.assertEqual(self.author_turn(brief)["verdict"], FAIL)
        self.assertEqual(self.author_turn(*bash(3, f"grep -n '{label}' skills/documentation-impact/SKILL.md"))["verdict"], FAIL)
        self.assertEqual(self.author_turn(done)["verdict"], PASS)
        self.assertEqual(self.author_turn(handoff)["verdict"], PASS)

    def test_copilot_a_brief_prescribing_one_label_is_not_an_author_result(self):
        for prompt in ("Review the docs. Report `Result: independent review required`.", "Return the author result: independent review required."):
            brief = {"seq": 2, "kind": "tool_call", "name": "Agent", "input": {"prompt": prompt}}
            self.assertEqual(self.author_turn(brief)["verdict"], FAIL, prompt)
        handoff = {"seq": 2, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": [{"context": "Role: trail reviewer.\n"
                   "- README was updated. Direct CLI and unit checks passed.\n- Author result: `independent review required` because the CLI changed."}]}}
        self.assertEqual(self.author_turn(handoff)["verdict"], PASS)

    def test_n7_a_recorded_not_required_result_reads_as_not_required(self):
        done = {"seq": 2, "kind": "tool_call", "name": "TodoWrite", "input": {"todos": [
            {"content": "Author result: independent review not required.", "status": "completed"}]}}
        result = self.author_turn(done, pid="documentation-impact-independent-review-pass-required")
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "author result: not required")

    def test_n7_a_slash_prefixed_skill_load_reads_the_bare_skill(self):
        events = [{"seq": 1, "kind": "tool_call", "name": "Skill", "input": {"skill": "/how"}}]
        self.assertEqual(oracles.View(minimal(events=events), load_case("how-run"), None).lead_reads(), ["how/SKILL.md"])

    def worklist_at(self, list_seq):
        events = ([read(1, "poteto-mode/playbooks/feature.md"), read(2, "unslop/SKILL.md"),
                   {"seq": 3, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "### Feature"},
                   {"seq": 4, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "name: unslop"}]
                  + bash(6, "ls") + bash(8, "cat tally/__main__.py") + [text(list_seq, "Worklist")])
        trace = minimal(events=events, worklist=[{"seq": list_seq, "carrier": "text", "items": feature_items()}])
        return grade("worklist-falls-back-to-numbered-list", trace, feature_case(env={"todo_tools": False}))

    def test_worklist_lands_after_the_playbook_read_and_before_the_next_tool_call(self):
        self.assertEqual(self.worklist_at(5)["verdict"], PASS)
        late = self.worklist_at(30)
        self.assertEqual(late["verdict"], FAIL, late)
        self.assertEqual(late["failures"], ["first numbered list at seq 30 is not between the playbook read (answered at seq 3) and the next tool call (seq 6)"])

    def test_runtime_encoding_needs_a_curated_subject(self):
        constraint = "do not remove: the sink needs a trailing newline on every row"
        reply = "the trailing newline is gone"
        for line in ('    do = "\\n"', '    for every in "\\n":', '    needs = "\\n"'):
            self.assertIsNone(oracles.encoding_landed({"rollup/export.py": line}, constraint, reply), line)
        self.assertEqual(oracles.encoding_landed({"rollup/sink.py": '        self.handle.write(row + "\\n")'}, constraint, reply),
                         "runtime: rollup/sink.py")
        self.assertIsNone(oracles.encoding_landed({"tests/test_export.py": "def test_done(): pass"}, constraint))
        self.assertEqual(oracles.encoding_landed({"tests/test_export.py": "assert out.endswith('\\n')"}, constraint), "tests/test_export.py")

    def sicko(self, reply):
        events = [{"seq": 3, "kind": "tool_call", "name": "Agent", "input": {"subagent_type": "comment-sicko"}, "id": "a"},
                  {"seq": 4, "kind": "tool_result", "name": "Agent", "ok": True, "output_head": "HA HA HA. Deleted 20 comments.", "id": "a"}]
        spawns = [{"seq": 3, "tool": "Agent", "subagent_type": "comment-sicko", "prompt_head": "Clean the diff."}]
        return grade("no-comments-spawns-comment-sicko", minimal(events=events, spawns=spawns, final_reply=reply), load_case("no-comments-run"))

    def test_batch9_an_empty_encoding_offers_line_is_not_an_offer(self):
        none = self.sicko("Removed 20 comments.\n- Architect sketch, reruns, encoding offers, encodings, and open work: none.")
        self.assertEqual(none["verdict"], INCONCLUSIVE, none)
        self.assertIn("encoding offer in reply: False", none["evidence"])
        offer = self.sicko("Removed 20 comments. The cheapest encoding is a sink test; say yes and I'll add it.")
        self.assertEqual(offer["verdict"], PASS, offer)

    def test_batch9_a_failing_assertion_is_a_check_that_ran(self):
        failing = bash(10, "python3 -m unittest tests.test_export", ok=False, head="FAIL: test_retry\nAssertionError: 8 != 7\nFAILED (failures=1)")
        green = bash(20, "python3 -m unittest tests.test_export", head="Ran 1 test\n\nOK")
        result = grade("reply-says-inconclusive-when-check-cannot-run", minimal(events=failing + green, final_reply="Fixed and verified."), load_case("bug-fix-run"))
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)

    def test_batch9_a_later_script_check_clears_a_check_that_could_not_run(self):
        case = load_case("bug-fix-run")
        cannot = bash(10, "python3 -m rollup data/orders.csv /tmp/out.csv", ok=False, head="ModuleNotFoundError: No module named 'rollup'")
        script = bash(20, "python3 /private/tmp/rollup-retry-check.py", head="ids 1001..1007 match")
        recovered = grade("reply-says-inconclusive-when-check-cannot-run", minimal(events=cannot + script, final_reply="Fixed and verified."), case)
        self.assertEqual(recovered["verdict"], INCONCLUSIVE, recovered)
        stuck = grade("reply-says-inconclusive-when-check-cannot-run", minimal(events=cannot, final_reply="Fixed and verified."), case)
        self.assertEqual(stuck["verdict"], FAIL, stuck)
        for note in ("git status  # python3 check.py", "git status  # python3 -m rollup data/orders.csv out.csv", "ls  # rerun unittest"):
            commented = grade("reply-says-inconclusive-when-check-cannot-run", minimal(events=cannot + bash(20, note), final_reply="Fixed and verified."), case)
            self.assertEqual(commented["verdict"], FAIL, note)

    def test_f16_a_lone_sleep_is_not_a_loop_facility(self):
        case = load_case("overnight-run")
        self.assertEqual(grade("autonomous-run-uses-loop-facility", minimal(events=bash(1, "python3 -m http.server & sleep 2; curl localhost:8000")), case)["verdict"], FAIL)
        self.assertEqual(grade("autonomous-run-uses-loop-facility", minimal(events=bash(1, "until curl -sf localhost:8000; do sleep 5; done")), case)["verdict"], PASS)

    def test_f16_waiting_or_approval_in_passing_is_not_a_pause(self):
        case = load_case("architect-checkpoint-run")
        passing = grade("architect-checkpoint-opt-in", minimal(final_reply="Design A chosen. The judge approved it; no step is waiting."), case)
        self.assertEqual(passing["verdict"], INCONCLUSIVE, passing)
        asked = grade("architect-checkpoint-opt-in", minimal(final_reply="Design A is in docs/design.md. Reply “approve” to implement it."), case)
        self.assertEqual(asked["verdict"], PASS, asked)

    def test_f16_reading_the_runner_prompt_alone_is_not_a_fan_out(self):
        case, pid = load_case("feature-boundary-run"), "poteto-mode-triggers-architect-on-boundary-crossing"
        events = [read(0, "poteto-mode/playbooks/feature.md"), read(1, "architect/references/runner-prompt.md")]
        self.assertEqual(grade(pid, minimal(events=events, final_reply="done"), case)["verdict"], FAIL)
        sealed = [{"seq": s, "tool": "spawn_agent", "x_prompt_encrypted": True} for s in (3, 4)]
        self.assertEqual(grade(pid, minimal(events=events, spawns=sealed, harness="codex", final_reply="done"), case)["verdict"], PASS)
        late = [read(0, "poteto-mode/playbooks/feature.md"), read(5, "architect/references/runner-prompt.md")]
        self.assertEqual(grade(pid, minimal(events=late, spawns=sealed, harness="codex", final_reply="done"), case)["verdict"], FAIL)

    def test_hermes_audit_the_keeps_going_count_names_its_turn(self):
        events = in_turn(0, [{"seq": 0, "kind": "user", "text": "going to bed"}] + bash(1, "ls")) + in_turn(1, [{"seq": 5, "kind": "user", "text": "catch up"}] + bash(6, "ls"))
        result = grade("session-override-keeps-going", minimal(events=events), load_case("overnight-run"))
        self.assertIn("tool calls in the first turn: 1", result["evidence"])


class Issue133SpawnsAndVerdicts(unittest.TestCase):
    def sealed(self, seq, reply, task="t"):
        return {"seq": seq, "tool": "spawn_agent", "model": "gpt-6.1-sol", "prompt_head": None, "x_prompt_encrypted": True,
                "x_child_first_reply": reply, "task_name": task}

    def spawned(self, spawns, gap_after=None):
        events = [{"seq": s["seq"], "kind": "tool_call", "name": "spawn_agent", "input": {"task_name": s["task_name"]}} for s in spawns]
        if gap_after is not None:
            events.insert(gap_after, text(20, "Both are back."))
        return events

    def test_n1_an_explorer_whose_first_reply_says_judge_still_explores(self):
        spawns = [self.sealed(10, "Explorer: I'll judge where the seams are."), self.sealed(10, "Explorer: tracing publish."), self.sealed(30, "Writing.")]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=self.spawned(spawns, 2), spawns=spawns, harness="codex"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_n1_runners_whose_first_replies_say_judge_or_synthesize_are_runners(self):
        spawns = [self.sealed(10, "Design runner: I'll judge which shape is simplest.", "runner_a"),
                  self.sealed(10, "### Sketch\n\nI'll synthesize the caller's view.", "runner_b")]
        trace = minimal(events=[read(1, "arena/SKILL.md")] + self.spawned(spawns), spawns=spawns, harness="codex")
        result = grade("architect-runs-arena-for-sketches", trace, load_case("architect-run"))
        self.assertIn("runner spawns: 2", result["evidence"])

    def test_n2_implementers_whose_first_replies_mention_source_control_are_not_investigators(self):
        spawns = [self.sealed(10, "I'll commit the change to source control when done."), self.sealed(10, "Pushing to source control after the edits.")]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=self.spawned(spawns), spawns=spawns, harness="codex"), load_case("why-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_n2_implementers_whose_first_replies_mention_explorer_notes_are_not_explorers(self):
        spawns = [delegate(10, "Implement the parser change in src/a.py.", "Implementing; the explorer notes say to edit src/a.py."),
                  delegate(10, "Implement the exporter change in src/b.py.", "Implementing; the explorer notes say to edit src/b.py."), delegate(30, "Write the answer.")]
        events = [{"seq": 10, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(20, "w"), {"seq": 30, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)

    def test_n2_an_implementer_whose_first_reply_mentions_explorer_notes_is_no_narrow_question_explorer(self):
        spawns = [self.sealed(10, "Implementing per the explorer notes in src/a.py.")]
        result = grade("how-narrow-question-no-explorers", minimal(events=self.spawned(spawns), spawns=spawns, harness="codex", final_reply="x"), load_case("how-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_n2_a_heading_labels_only_itself_except_the_investigator_source(self):
        spawns = [delegate(10, "Implement the parser change in src/a.py.", "### Update\nUsing the explorer notes, I implemented the parser."),
                  delegate(10, "Implement the exporter change in src/b.py.", "### Update\nUsing the explorer notes, I implemented the exporter."),
                  delegate(30, "Write the answer.")]
        events = [{"seq": 10, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(20, "w"), {"seq": 30, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        result = grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))
        self.assertEqual(result["verdict"], FAIL, result)
        sourced = [self.sealed(10, "### Source\nSource control: git log and blame on relay/cache.py.")]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=self.spawned(sourced), spawns=sourced, harness="codex"), load_case("why-run"))
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")

    def test_an_unlabelled_first_reply_still_names_a_sealed_reviewer(self):
        reviewer = self.sealed(5, "persona: poteto-agent\nI'm using poteto-mode and documentation-impact to review the CLI and its docs.", "docs_review")
        events = [dict(e, turn=0) for e in self.spawned([reviewer])] + [dict(text(7, "Done. Author result: independent review required. Review: pass."), turn=0),
                                                                        dict(text(9, "Review mode run."), turn=1)]
        result = grade("documentation-impact-independent-review-pass-required", minimal(events=events, spawns=[dict(reviewer, turn=0)], harness="codex"),
                       load_case("doc-impact-run"))
        self.assertEqual(result["verdict"], PASS, result)

    def sources(self, reply):
        return grade("how-why-reports-name-sources-searched", minimal(final_reply=reply), load_case("why-run"))["verdict"]

    def test_n4_a_single_cited_source_is_not_a_sources_section(self):
        self.assertEqual(self.sources("Source: commit 12d7ece."), FAIL)
        self.assertEqual(self.sources("Commit 12d7ece raised it.\n\nSources: git log, README."), PASS)

    def test_n7_a_source_label_must_start_a_sentence(self):
        self.assertEqual(self.sources("Commit 12d7ece pulled from two open sources: the upstream git mirror and a fork."), FAIL)

    def test_n7_sources_searched_mid_sentence_is_a_sources_section(self):
        self.assertEqual(self.sources("Commit 12d7ece raised it. I listed the sources searched below, git log first."), PASS)

    def judged(self, judge, lead, models):
        spawns = [{"seq": 10 + n, "tool": "Agent", "model": m, "prompt_head": "Candidate design"} for n, m in enumerate(models)]
        spawns.append({"seq": 30, "tool": "Agent", "model": judge, "prompt_head": "READ-ONLY. You are the judge scoring candidates against the rubric."})
        trace = minimal(events=[{"seq": s["seq"], "kind": "tool_call", "name": "Agent", "input": {}} for s in spawns], spawns=spawns)
        trace["model"] = lead
        return grade("arena-readonly-cross-judge", trace, load_case("arena-run"))["verdict"]

    def test_n6_a_slug_with_no_tier_token_cannot_be_compared(self):
        self.assertEqual(self.judged("claude", "claude-opus-5-5", ["opus", "sonnet"]), INCONCLUSIVE)
        self.assertEqual(self.judged("gpt-6", "gpt-6.1-sol", ["gpt-6.1-sol", "gpt-6-luna"]), INCONCLUSIVE)
        self.assertEqual(self.judged("opus", "claude", ["opus", "sonnet"]), INCONCLUSIVE)

    def test_n6_inherit_is_the_leads_model(self):
        self.assertEqual(self.judged("inherit", "claude-opus-5-5", ["opus", "sonnet"]), FAIL)
        self.assertEqual(self.judged("opus", "claude-opus-5-5", ["inherit", "inherit"]), PASS)

    def test_n7_two_tierless_slugs_compare_whole(self):
        self.assertEqual(self.judged("claude", "claude", ["gpt-6"]), FAIL)

    def test_a_labelled_first_reply_names_a_sealed_investigator(self):
        spawns = [self.sealed(10, "Source investigated: local Git history, README, and source comments.")]
        result = grade("why-queries-evidence-categories-in-parallel", minimal(events=self.spawned(spawns), spawns=spawns, harness="codex"), load_case("why-run"))
        self.assertEqual(result["evidence"][0], "investigator spawns: 1")

    def arena(self, line):
        candidates = [{"seq": 43, "tool": "delegate_task", "prompt_head": f"Design one candidate {n}. Write under /tmp/k/candidate-{n}/"} for n in range(1, 6)]
        judge = {"seq": 49, "tool": "delegate_task", "prompt_head": "Independently cross-judge all five candidates. Read-only."}
        events = [{"seq": 43, "kind": "tool_call", "name": "delegate_task", "input": {}}, {"seq": 49, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        trace = minimal(events=events, spawns=candidates + [judge], final_reply=f"Arena result\n- {line}\n- Verified: 8 unit tests passed.", harness="hermes")
        return grade("arena-fans-out-and-grafts", trace, load_case("arena-run"))["verdict"]

    def test_f14_based_and_database_do_not_name_a_base(self):
        for line in ("Based on the judge, retries were grafted from candidate 3.", "The database layer was grafted from candidate 3."):
            self.assertEqual(self.arena(line), FAIL, line)
        self.assertEqual(self.arena("Candidate 1 is the base; retries were grafted from candidate 3."), PASS)

    def test_n10_a_negation_anywhere_in_the_picks_clause_cancels_it(self):
        for line in ("It was not at any point in the long review the case that candidate 1 was selected, with retries grafted from candidate 3.",
                     "Nobody picked candidate 1, and retries were grafted from candidate 3.",
                     "None of us selected candidate 1, and retries were grafted from candidate 3.",
                     "We never selected candidate 1, and retries were grafted from candidate 3.",
                     "Neither of us selected candidate 1, and retries were grafted from candidate 3."):
            self.assertEqual(self.arena(line), FAIL, line)

    def test_n10_each_clause_split_ends_an_earlier_negation(self):
        for split in (". ", ", ", "; ", ": ", "\n- ", " but ", " and ", " so ", " because ", " since ", " although ", " though ",
                      " while ", " yet ", " then ", " which "):
            line = f"Candidate 2 was not chosen{split}candidate 1 was selected with retries grafted from candidate 3."
            self.assertEqual(self.arena(line), PASS, repr(split))

    def lead_reads(self, brief, reads):
        spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in (1, 2, 3, 4, 5)]
        spawns.append({"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."})
        events = [{"seq": s, "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in (1, 2, 3, 4, 5, 9)]
        events += [e for n, command in enumerate(reads) for e in bash(20 + 2 * n, command)]
        return grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))

    def test_one_rationale_read_five_times_is_one_read(self):
        result = self.lead_reads("Write `rationale.md` in your directory.", ["cat /tmp/k/c1/rationale.md", "cat /tmp/k/c1//rationale.md"] + ["cat /tmp/k/c1/./rationale.md"] * 3
                                 + ["cat /tmp/k/c1/relay/cache.py"])
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["evidence"][0], "rationale files read after the last candidate spawn: 1")

    def test_an_assigned_text_rationale_counts(self):
        result = self.lead_reads("Save your reasoning to `decision.txt`.", [f"cat /tmp/k/c{n}/decision.txt" for n in range(1, 6)] + ["cat /tmp/k/c1/relay/cache.py"])
        self.assertEqual(result["verdict"], PASS, result)

    def tracers(self, heads):
        spawns = [delegate(27, h) for h in heads] + [delegate(41, "Write the answer.")]
        events = [{"seq": 27, "kind": "tool_call", "name": "delegate_task", "input": {}}, text(35, "done"),
                  {"seq": 41, "kind": "tool_call", "name": "delegate_task", "input": {}}]
        return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="hermes"), load_case("how-wide-run"))["verdict"]

    def test_a_read_only_tracer_that_leaves_synthesis_to_the_lead_explores(self):
        self.assertEqual(self.tracers(["Trace the ingest stage. Read-only: do not edit or write files. The lead handles synthesis.",
                                       "Trace the render stage. Read-only: do not edit or write files. The lead handles synthesis."]), PASS)

    def test_a_polite_edit_order_is_not_read_only(self):
        self.assertEqual(self.tracers(["Read-only: do not edit files. Please implement the parser.", "Read-only: do not edit files. Trace the store."]), FAIL)

    def review_verdict(self, line):
        trace = minimal(events=[dict(text(1, f"Done. Author result: independent review required. {line}"), turn=0), dict(text(3, "Review mode run."), turn=1)],
                        spawns=[{"seq": 1, "tool": "Agent", "prompt_head": "Role: trail reviewer. Independent review of the docs.", "turn": 0}])
        return grade("documentation-impact-independent-review-pass-required", trace, load_case("doc-impact-run"))["verdict"]

    def test_review_wording_that_is_not_a_pass(self):
        for line in ("The reviewer refused to pass it.", "The review would pass only with README changes.", "The review is unlikely to pass.",
                     "The review failed. Tests pass.", "The review did not, in the end, pass.", "No review has passed yet.",
                     "No independent reviewer has said pass.", "Neither review passed.", "The review cannot reasonably be said to have passed."):
            self.assertEqual(self.review_verdict(line), FAIL, line)

    def test_review_wording_that_ends_in_a_pass(self):
        for line in ("Review failed twice before it passed.", "The review did not pass at first, then passed.", "The review did not stall. Pass.",
                     "The review failed then passed.", "The review was not quick but passed."):
            self.assertEqual(self.review_verdict(line), PASS, line)

    def candidates_then_status(self, status):
        def task(n):
            return {"goal": "Design one cache-key candidate.", "context": f"Write only under /w/tmp/arena/candidate-{n}/: cache.py, rationale.md."}
        events = [{"seq": 43, "kind": "tool_call", "name": "delegate_task", "input": {"tasks": [task(n) for n in range(1, 6)]}}]
        events += [{"seq": 45, "kind": "tool_call", "name": "terminal", "input": {"command": "git status --short", "workdir": "/w/relay"}},
                   {"seq": 46, "kind": "tool_result", "name": "terminal", "ok": True, "output_head": json.dumps({"output": status, "exit_code": 0})}]
        spawns = [{"seq": 43, "tool": "delegate_task", "prompt_head": "Design one cache-key candidate."} for _ in range(5)]
        return grade("arena-candidates-own-worktrees", minimal(events=events, spawns=spawns, harness="hermes", cwd="/w/relay"), load_case("arena-run"))

    def test_a_candidate_write_into_the_parent_checkout_is_not_its_own_worktree(self):
        dirty = self.candidates_then_status("M README.md\n M relay/cache.py\n?? .arena/")
        self.assertEqual(dirty["verdict"], FAIL, dirty)
        clean = self.candidates_then_status("")
        self.assertEqual(clean["verdict"], PASS, clean)

    def test_copilot_an_untracked_or_unmerged_parent_file_is_a_candidate_write(self):
        for status in ("?? relay/key_format.py", "UU relay/cache.py", "DU tests/test_cache.py"):
            self.assertEqual(self.candidates_then_status(status)["verdict"], FAIL, status)
        own = self.candidates_then_status("?? decisions.tsv\n?? .worktrees/\n?? .arena/\n?? scratch_notes.md\n?? .claude/")
        self.assertEqual(own["verdict"], PASS, own)

    def test_swarm_ownership_past_the_prompt_head_counts(self):
        packages = ("ingest", "shape", "render", "publish")
        prompts = {p: "Goal: run one package's check script and report the result.\n" + "Repo: /w/kiln. Record the SHA first. " * 8
                   + f"Your slice is `packages/{p}` only." for p in packages}
        events = [{"seq": 8 + 2 * n, "kind": "tool_call", "name": "Agent", "input": {"description": "Check one package", "prompt": prompts[p]}}
                  for n, p in enumerate(packages)]
        spawns = [{"seq": e["seq"], "tool": "Agent", "prompt_head": e["input"]["prompt"][:300]} for e in events]
        self.assertTrue(all(p not in s["prompt_head"] for p, s in zip(packages, spawns)))
        result = grade("swarm-fans-out-and-aggregates", minimal(events=events, spawns=spawns, final_reply="One report."), load_case("swarm-run"))
        self.assertEqual(result["verdict"], PASS, result)


if __name__ == "__main__":
    unittest.main()

