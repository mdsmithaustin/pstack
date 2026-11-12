import json
import unittest
from pathlib import Path

import oracles
from harnesses import codex
from oracles import FAIL, INCONCLUSIVE, PASS

PID = "codex-spawns-state-fork-turns"
CASE = json.loads((Path(__file__).resolve().parent / "cases" / "delegate-fresh-context-run" / "case.json").read_text(encoding="utf-8"))
CURRENT, OLDER = "collaboration", "multi_agent_v1"
MADE = {CURRENT: '{"task_name":"/root/helper"}', OLDER: '{"agent_id":"019a6f2e","nickname":"Ada"}'}
NO_RESULT = object()
MISSING_TASK_NAME = "failed to parse function arguments: missing field `task_name`"
REFUSALS = (
    MISSING_TASK_NAME,
    "failed to parse function arguments: unknown field `fork_turn`, expected one of `message`, `task_name`",
    "fork_context is not supported in MultiAgentV2; use fork_turns instead",
    "fork_turns must be `none` or `all`",
    "fork_turns must be `none`, `all`, or a positive integer string",
    "Empty message can't be sent to an agent",
    "Provide either message or items, but not both",
    "Provide one of: message or items",
    "Items can't be empty",
    "Agent depth limit reached. Solve the task yourself.",
    "Full-history forked agents inherit the parent agent type; omit agent_type, or spawn without a full-history fork.",
    "Reasoning effort `xhigh` is not supported for model `gpt-5.6-luna`. Supported reasoning efforts: low, medium",
    "collab spawn failed: agent thread limit reached",
    "agent path `/root/helper` already exists",
)
UNPROVEN_RESULTS = (
    NO_RESULT, "aborted", "aborted by user after 3.2s", "Wall time: 3.2 seconds\naborted by user", "", "  ", "unsupported call: spawn_agent",
    "collab spawn failed: stream disconnected", "agent path must not be empty", "Reasoning effort is not supported", " " + MISSING_TASK_NAME,
    '{"ok":true}', '{"task_name":5}', '{"agent_id":null}', '{"task_name":"/root/helper","agent_id":"019a6f2e"}', '{"task_name":"/root/hel',
    '["task_name"]', '"task_name"', "null", "3", "9" * 5000, "[" * 100000,
    {"task_name": "/root/helper"}, ["task_name"], 5, 1.5, True, None,
)
JSON_VALUES = ("none", "all", "3", "", "trail reviewer", 0, 3, -1, 1.5, 1e308, True, False, None, [], ["all"], [None], {}, {"text": "all"},
               [{"type": "text", "text": "count"}], [{"text": 5}])


def call(arguments, result="made", namespace=CURRENT):
    return {"arguments": arguments, "namespace": namespace, "output": MADE[namespace] if result == "made" else result}


def v2(fork_turns=None, result="made", **fields):
    stated = {} if fork_turns is None else {"fork_turns": fork_turns}
    return call({"message": "count the TODO comments", "task_name": "helper", **stated, **fields}, result)


def v1(result="made", **fields):
    return call({"message": "count the TODO comments", **fields}, result, OLDER)


def grade_lines(lines, case=None, harness="codex"):
    lead = codex.harvest_rollout("".join(line + "\n" for line in lines).encode())
    trace = {"harness": harness, "cli_version": lead["meta"].get("cli_version"), "model": "m", "effort": "high", "exit_code": 0,
             "entry": "injected", "events": lead["events"], "worklist": [], "spawns": lead["spawns"], "files_read": [], "final_reply": ""}
    return oracles.check(PID, trace, case or {"entry": "poteto-mode"}, None)


def meta_line(release="0.167.0"):
    return json.dumps({"type": "session_meta", "payload": {"cwd": "/w", "id": "s", "cli_version": release}})


def grade_rollout(*calls, case=None, release="0.167.0", harness="codex"):
    rows = []
    for index, spawn in enumerate(calls):
        arguments = spawn["arguments"]
        payload = {"type": "function_call", "name": spawn.get("name", "spawn_agent"), "call_id": f"call-{index}",
                   "arguments": json.dumps(arguments) if isinstance(arguments, dict) and spawn.get("encode", True) else arguments}
        if spawn["namespace"] is not None:
            payload["namespace"] = spawn["namespace"]
        rows.append({"type": "response_item", "payload": payload})
        if spawn["output"] is not NO_RESULT:
            rows.append({"type": "response_item", "payload": {"type": "function_call_output", "call_id": f"call-{index}",
                                                              "output": spawn["output"]}})
    return grade_lines([meta_line(release), *(json.dumps(row) for row in rows)], case, harness)


class ToolIdentity(unittest.TestCase):
    def test_older_tool_child_is_fresh_though_the_call_names_a_task(self):
        result = grade_rollout(call({"message": "count TODOs", "task_name": "helper"}, namespace=OLDER), case=CASE)
        self.assertEqual(result["verdict"], PASS)
        self.assertIn("older spawn tool", result["evidence"][0])

    def test_older_tool_fork_fails_a_fresh_case_though_the_call_names_a_task(self):
        result = grade_rollout(call({"message": "list functions", "task_name": "helper", "fork_context": True}, namespace=OLDER),
                               v1(fork_context=False), case=CASE)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(len(result["failures"]), 1)
        self.assertIn("seq 0 carries lead history (fork_context=True)", result["failures"][0])

    def test_current_tool_call_refused_for_a_missing_task_name_made_no_child(self):
        refused = call({"message": "list functions", "fork_context": True}, MISSING_TASK_NAME)
        result = grade_rollout(refused, case=CASE)
        self.assertEqual(result["verdict"], INCONCLUSIVE)
        self.assertIn("Codex refused every recorded spawn_agent call", result["failures"][0])
        self.assertEqual(grade_rollout(refused, v2("none"), case=CASE)["verdict"], PASS)

    def test_result_decides_the_tool_whatever_keys_the_call_shows(self):
        for arguments, by_tool in (
                ({"message": "m", "task_name": "helper"}, {CURRENT: FAIL, OLDER: PASS}),
                ({"message": "m"}, {OLDER: PASS}),
                ({"message": "m", "task_name": "helper", "fork_turns": "all"}, {CURRENT: FAIL, OLDER: PASS}),
                ({"message": "m", "task_name": "helper", "fork_turns": "none", "fork_context": True}, {CURRENT: INCONCLUSIVE, OLDER: FAIL}),
                ({"message": "m", "task_name": "helper", "fork_turns": "none", "fork_context": False}, {CURRENT: INCONCLUSIVE, OLDER: PASS})):
            for tool, verdict in by_tool.items():
                with self.subTest(arguments=arguments, tool=tool):
                    self.assertEqual(grade_rollout(call(arguments, MADE[tool], tool), case=CASE)["verdict"], verdict)

    def test_result_recorded_as_content_items_counts(self):
        for tool, verdict in ((CURRENT, FAIL), (OLDER, PASS)):
            with self.subTest(tool=tool):
                items = [{"type": "input_text", "text": MADE[tool][:9]}, {"type": "input_text", "text": MADE[tool][9:]}]
                self.assertEqual(grade_rollout(call(v2()["arguments"], items, tool), case=CASE)["verdict"], verdict)

    def test_result_decides_the_tool_under_any_namespace_that_does_not_contradict_it(self):
        for namespace in (None, CURRENT, "team_tools", "multi_agent_v1x", 5, ["multi_agent_v1"], {"a": 1}, True, 1.5, ""):
            with self.subTest(namespace=namespace):
                self.assertEqual(grade_rollout(call(v2()["arguments"], MADE[CURRENT], namespace))["verdict"], FAIL)
                self.assertEqual(grade_rollout(call(v2()["arguments"], MADE[OLDER], namespace), case=CASE)["verdict"], PASS)

    def test_current_tool_result_under_the_older_tools_namespace_is_inconclusive(self):
        for spawn in (v2(), v2("all"), v2("none")):
            with self.subTest(arguments=spawn["arguments"]):
                result = grade_rollout(call(spawn["arguments"], MADE[CURRENT], OLDER), v2("none"), case=CASE)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("seq 0 has no recorded result that proves which spawn tool ran", result["failures"][0])

    def test_both_tools_in_one_session_are_each_graded_by_their_own_result(self):
        self.assertEqual(grade_rollout(v2("none"), v1(), v1(fork_context=False), case=CASE)["verdict"], PASS)
        result = grade_rollout(v2("none"), v1(fork_turns="none", fork_context=True), v2(), case=CASE)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual([failure.split(" carries ")[0].split(" omits ")[0] for failure in result["failures"]],
                         ["spawn at seq 2", "spawn at seq 4"])

    def test_result_that_proves_no_tool_and_no_refusal_is_inconclusive(self):
        for output in UNPROVEN_RESULTS:
            for arguments in (v2("all")["arguments"], v2()["arguments"], v2("none")["arguments"], v1(fork_context=True)["arguments"]):
                with self.subTest(output=str(output)[:40], arguments=arguments):
                    result = grade_rollout(call(arguments, output), v2("none"), case=CASE)
                    self.assertEqual(result["verdict"], INCONCLUSIVE)
                    self.assertIn("seq 0 has no recorded result that proves which spawn tool ran", result["failures"][0])

    def test_long_result_is_read_whole(self):
        made = '{"task_name":"/root/' + "worker/" * 80 + 'helper"}'
        self.assertEqual(grade_rollout(call(v2()["arguments"], made))["verdict"], FAIL)
        self.assertEqual(grade_rollout(call(v2("none")["arguments"], made), case=CASE)["verdict"], PASS)

    def test_result_of_another_tool_is_not_a_spawn_result(self):
        shell = {**call({"cmd": "ls"}, MADE[CURRENT]), "name": "shell"}
        self.assertEqual(grade_rollout(v2("none"), shell, v2("none", NO_RESULT), shell, case=CASE)["verdict"], INCONCLUSIVE)
        self.assertEqual(grade_rollout(shell, v2("none"), shell, case=CASE)["verdict"], PASS)

    def test_created_child_whose_arguments_the_adapter_cannot_read_is_inconclusive(self):
        forked = '{"message": "m", "fork_context": true, "ignored": ' + "9" * 5000 + "}"
        for arguments in (forked, '{"message": "m", "fork_context": true, "ignored": ' + "[" * 100000 + "]" * 100000 + "}", "not json", "[1]", "3",
                          '"all"', "null"):
            for tool in (OLDER, CURRENT):
                with self.subTest(arguments=arguments[:40], tool=tool):
                    spawn = {**call({}, MADE[tool], tool), "arguments": arguments, "encode": False}
                    result = grade_rollout(spawn, v2("none"), case=CASE)
                    self.assertEqual(result["verdict"], INCONCLUSIVE)
                    self.assertIn("seq 0 created a child, yet its arguments are not a JSON object the adapter can read", result["failures"][0])
        for arguments in ({"value": 3, "message": "m"}, {"raw": "x", "message": "m"}):
            with self.subTest(arguments=arguments):
                self.assertEqual(grade_rollout(call(arguments, namespace=OLDER), case=CASE)["verdict"], PASS)
                self.assertEqual(grade_rollout({**call(arguments, namespace=OLDER), "encode": False}, case=CASE)["verdict"], PASS)

    def test_proven_failure_outranks_an_unproven_call(self):
        self.assertEqual(grade_rollout(v2("all", NO_RESULT), v2())["verdict"], FAIL)

    def test_accepted_call_with_a_value_its_tool_refuses_is_inconclusive(self):
        for spawn in (v2(3), v2(True), v2(["all"]), v2(1.5), v2("0"), v2("-1"), v2("some"), v2("²"), v2("1.5"), v2("\u0663"), v2("\x1fall"), v2("\x1fnone"),
                      v2("none", fork_context=False), v2("none", fork_context=True), v2("18446744073709551616"), v2("9" * 4301),
                      v1(fork_context="true"), v1(fork_context=None), v1(fork_context=0), v1(fork_context=1), v1(fork_context=[]), v1(fork_context={})):
            with self.subTest(arguments=str(spawn["arguments"])[:80]):
                result = grade_rollout(spawn, v2("none"), case=CASE)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("is a value that tool refuses in every release checked", result["failures"][0])
        self.assertIn("fork_turns=a list is a value", grade_rollout(v2(["all"]))["failures"][0])
        self.assertIn("fork_context=True is a value", grade_rollout(v2("none", fork_context=True))["failures"][0])
        self.assertIn("fork_context=None is a value", grade_rollout(v1(fork_context=None))["failures"][0])

    def test_null_fork_context_on_the_current_tool_reads_as_absent(self):
        self.assertEqual(grade_rollout(v2("none", fork_context=None), case=CASE)["verdict"], PASS)
        self.assertEqual(grade_rollout(v2("all", fork_context=None), case=CASE)["verdict"], FAIL)


class RefusedCalls(unittest.TestCase):
    def test_known_refusal_is_not_a_fork(self):
        for refusal in REFUSALS:
            for spawn in (v2("all", refusal, model="gpt-6-sol"), v2(None, refusal), v1(refusal, fork_context=True, agent_type="default")):
                with self.subTest(refusal=refusal, arguments=spawn["arguments"]):
                    result = grade_rollout(spawn, case=CASE)
                    self.assertEqual(result["verdict"], INCONCLUSIVE)
                    self.assertIn("Codex refused every recorded spawn_agent call", result["failures"][0])
                    self.assertEqual(grade_rollout(spawn, v2("none"), case=CASE)["verdict"], PASS)

    def test_refusal_for_a_reason_the_arguments_do_not_show_is_not_a_fork(self):
        unknown_field = call({"task_name": "h1", "message": "x", "fork_turns": "all", "fork_turn": "none"}, REFUSALS[1])
        self.assertEqual(grade_rollout(unknown_field, v2("none"), case=CASE)["verdict"], PASS)
        self.assertEqual(grade_rollout(v2("all", "collab spawn failed: agent thread limit reached"), v2("none"), case=CASE)["verdict"], PASS)

    def test_refusal_beside_a_fork_does_not_clear_it(self):
        self.assertEqual(grade_rollout(v2("all", MISSING_TASK_NAME), v2("all"), case=CASE)["verdict"], FAIL)


class CurrentTool(unittest.TestCase):
    def test_omitted_or_empty_field_fails_as_a_full_fork(self):
        for omitted in (None, "", "  ", "\u3000\x85"):
            with self.subTest(omitted=omitted):
                result = grade_rollout(v2("none"), v2(omitted))
                self.assertEqual(result["verdict"], FAIL)
                self.assertEqual(len(result["failures"]), 1)
                self.assertIn("seq 2 omits fork_turns", result["failures"][0])
        self.assertEqual(grade_rollout(call({"message": "m", "task_name": "helper", "fork_turns": None}))["verdict"], FAIL)

    def test_fresh_spawns_pass(self):
        self.assertEqual(grade_rollout(v2("none", model="gpt-6-sol", reasoning_effort="high"), v2("none"))["verdict"], PASS)
        self.assertEqual(grade_rollout(v2("none", agent_type="trail reviewer"), case=CASE)["verdict"], PASS)

    def test_value_is_read_as_codex_reads_it(self):
        for stated in (" none ", "None", "NONE\n", "\u2003none\xa0"):
            with self.subTest(stated=stated):
                self.assertEqual(grade_rollout(v2(stated, model="gpt-6-sol"))["verdict"], PASS)
        for stated in (" all ", "ALL", "\u2003all\xa0"):
            with self.subTest(stated=stated):
                self.assertEqual(grade_rollout(v2(stated, model="gpt-6-sol"))["verdict"], FAIL)

    def test_full_fork_with_a_model_or_effort_fails_on_every_release(self):
        for pinned, release in (({"model": "gpt-6-sol"}, "0.167.0"), ({"reasoning_effort": "high"}, "0.161.0"), ({"model": "gpt-6-sol"}, None)):
            with self.subTest(pinned=pinned, release=release):
                result = grade_rollout(v2("all", **pinned), release=release)
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("forks the full history while passing", result["failures"][0])

    def test_fork_whose_permission_the_trace_does_not_prove_is_inconclusive(self):
        for spawn in (v2("all", message="draft the resume note"), v2("3"), v2("all", agent_type="default"), v2("all", agent_type="poteto-agent"),
                      v2("all", message="Please review the diff on branch x."), v2("all", task_name="review_diff"),
                      v2("all", message="Draft the note. The trail reviewer role reads it next."), v1(fork_context=True)):
            with self.subTest(arguments=spawn["arguments"]):
                result = grade_rollout(spawn)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("does not prove whether the fork restrictions permit it", result["failures"][0])

    def test_case_that_needs_no_history_rejects_any_fork(self):
        self.assertEqual(grade_rollout(v2("none"), case=CASE)["verdict"], PASS)
        for carried in ("all", "2", "18446744073709551615"):
            for release in ("0.161.0", "0.167.0"):
                with self.subTest(carried=carried, release=release):
                    result = grade_rollout(v2(carried), case=CASE, release=release)
                    self.assertEqual(result["verdict"], FAIL)
                    self.assertIn("on a task whose brief needs none", result["failures"][0])

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
        for release in ("0.162.0", "0.167.0", "codex-cli 0.167.2", "1.0.0", " 0.167.0\n"):
            for count in ("3", "+3", "03", " 3 ", "18446744073709551615"):
                with self.subTest(release=release, count=count):
                    result = grade_rollout(v2(count, model="gpt-6-sol"), release=release)
                    self.assertEqual(result["verdict"], FAIL)
                    self.assertIn("forks the full history while passing model", result["failures"][0])

    def test_count_with_a_model_is_unknown_where_the_trace_names_no_release_that_ignores_counts(self):
        for release in ("0.161.0", "0.161.9", "0.130.0", "0.163.0-alpha.3", "0.167.0-alpha.3.2", "0.167", "v0.167.0", "0.167.0.1", "1.0.167.0",
                        "codex 0.167.0", "9" * 5000 + ".0.0", "0." + "9" * 5000 + ".0", "", None, 167, 0.167, True, ["0.167.0"],
                        {"version": "0.167.0"}):
            with self.subTest(release=str(release)[:30]):
                result = grade_rollout(v2("3", model="gpt-6-sol"), release=release)
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("passes a turn count with model", result["failures"][0])

    def test_count_into_a_reviewer_fails_on_every_release(self):
        for release in ("0.161.0", "0.167.0", None):
            with self.subTest(release=release):
                result = grade_rollout(v2("2", agent_type="trail reviewer"), release=release)
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("reviewer spawn", result["failures"][0])


class OlderTool(unittest.TestCase):
    def test_fresh_child_passes_whether_or_not_the_call_states_it(self):
        for spawn in (v1(fork_context=False, model="gpt-5.6-luna", agent_type="trail reviewer"), v1(model="gpt-5.6-luna"),
                      v1(fork_context=False, fork_turns="all", model="gpt-5.6-luna")):
            with self.subTest(arguments=spawn["arguments"]):
                self.assertEqual(grade_rollout(spawn, case=CASE)["verdict"], PASS)

    def test_fork_fails_where_a_full_fork_may_not_run(self):
        for spawn, case, said in ((v1(fork_context=True, model="gpt-5.6-luna"), None, "forks the full history while passing model"),
                                  (v1(fork_context=True, reasoning_effort="low"), None, "forks the full history while passing effort"),
                                  (v1(fork_context=True, agent_type="trail reviewer"), None, "reviewer spawn"),
                                  (v1(fork_context=True), CASE, "on a task whose brief needs none")):
            with self.subTest(said=said):
                result = grade_rollout(spawn, case=case)
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn(said, result["failures"][0])


class ReviewSeat(unittest.TestCase):
    def test_agent_type_the_adapter_assigns_to_a_review_seat_must_start_fresh(self):
        for seat in ("trail reviewer", " trail reviewer\n"):
            with self.subTest(seat=seat):
                result = grade_rollout(v2("all", agent_type=seat))
                self.assertEqual(result["verdict"], FAIL)
                self.assertIn("reviewer spawn at seq 0 carries lead history (fork_turns='all')", result["failures"][0])
                self.assertEqual(grade_rollout(v2("none", agent_type=seat))["verdict"], PASS)

    def test_seat_the_call_does_not_assign_is_not_a_proven_reviewer(self):
        for fields in ({"agent_type": "Trail Reviewer"}, {"agent_type": "trail reviewer fixer"}, {"agent_type": "code-review-fixer"},
                       {"agent_type": "reviewer"}, {"agent_type": "poteto-agent"}, {"agent_type": "\x1ftrail reviewer"},
                       {"agent_type": 5}, {"agent_type": True}, {"agent_type": ["trail reviewer"]}, {"agent_type": {"name": "trail reviewer"}},
                       {"message": "Print persona: trail-reviewer on its own line first."},
                       {"message": "You are the trail reviewer. Review the diff."}, {"task_name": "trail_reviewer"}):
            with self.subTest(fields=fields):
                result = grade_rollout(v2("all", **fields))
                self.assertEqual(result["verdict"], INCONCLUSIVE)
                self.assertIn("does not prove whether the fork restrictions permit it", result["failures"][0])


class AnyJsonValue(unittest.TestCase):
    FIELDS = ("message", "prompt", "items", "task_name", "fork_turns", "fork_context", "agent_type", "model", "reasoning_effort")
    RESULTS = (MADE[CURRENT], MADE[OLDER], MISSING_TASK_NAME, NO_RESULT)
    VERDICTS = (PASS, FAIL, INCONCLUSIVE)

    def test_every_json_type_in_every_spawn_field_gets_a_verdict(self):
        for field in self.FIELDS:
            for value in JSON_VALUES:
                for result in self.RESULTS:
                    for case in (None, CASE):
                        with self.subTest(field=field, value=value, result=str(result)[:20], fresh=bool(case)):
                            arguments = {"message": "count", "task_name": "helper", "fork_turns": "all", field: value}
                            self.assertIn(grade_rollout(call(arguments, result), v2("3", model="m"), case=case)["verdict"], self.VERDICTS)

    def test_every_json_type_as_the_arguments_gets_a_verdict(self):
        for arguments in (*JSON_VALUES, "not json", "[1]", '"all"', '{"fork_turns": ' + "9" * 5000 + "}", "[" * 100000,
                          '{"message": ' + "[" * 100000 + "}"):
            for result in self.RESULTS:
                with self.subTest(arguments=str(arguments)[:30], result=str(result)[:20]):
                    spawn = {**call({}, result), "arguments": arguments, "encode": False}
                    self.assertIn(grade_rollout(spawn, v2("none"), case=CASE)["verdict"], self.VERDICTS)

    def test_every_json_type_as_the_result_or_namespace_gets_a_verdict(self):
        for value in JSON_VALUES:
            with self.subTest(value=value):
                self.assertIn(grade_rollout(call(v2("all")["arguments"], value), case=CASE)["verdict"], self.VERDICTS)
                self.assertIn(grade_rollout(call(v2("all")["arguments"], MADE[CURRENT], value), case=CASE)["verdict"], self.VERDICTS)

    def test_nesting_past_the_parser_limit_in_any_position_gets_a_verdict(self):
        for depth in (50, 400, 900, 990, 1000, 1100, 5000, 100000):
            nested = "[" * depth + "]" * depth
            arguments = json.dumps('{"message": "m", "task_name": "t", "fork_turns": ' + nested + "}")
            lines = {
                "argument value": ['{"type":"response_item","payload":{"type":"function_call","name":"spawn_agent","call_id":"c","arguments":'
                                   + arguments + "}}",
                                   '{"type":"response_item","payload":{"type":"function_call_output","call_id":"c","output":'
                                   + json.dumps(MADE[CURRENT]) + "}}"],
                "arguments": ['{"type":"response_item","payload":{"type":"function_call","name":"spawn_agent","call_id":"c","arguments":'
                              + nested + "}}"],
                "result": ['{"type":"response_item","payload":{"type":"function_call","name":"spawn_agent","call_id":"c","arguments":'
                           + json.dumps(json.dumps(v2("all")["arguments"])) + "}}",
                           '{"type":"response_item","payload":{"type":"function_call_output","call_id":"c","output":{"task_name":'
                           + nested + "}}}"],
                "result text": ['{"type":"response_item","payload":{"type":"function_call","name":"spawn_agent","call_id":"c","arguments":'
                                + json.dumps(json.dumps(v2("all")["arguments"])) + "}}",
                                '{"type":"response_item","payload":{"type":"function_call_output","call_id":"c","output":'
                                + json.dumps('{"task_name":' + nested + "}") + "}}"],
                "release": ['{"type":"session_meta","payload":{"cwd":"/w","id":"s","cli_version":' + nested + "}}",
                            json.dumps({"type": "response_item", "payload": {
                                "type": "function_call", "name": "spawn_agent", "call_id": "c",
                                "arguments": json.dumps(v2("3", model="m")["arguments"])}}),
                            json.dumps({"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c",
                                                                             "output": MADE[CURRENT]}})],
            }
            for position, rows in lines.items():
                with self.subTest(depth=depth, position=position):
                    head = [] if position == "release" else [meta_line()]
                    self.assertIn(grade_lines(head + rows, CASE)["verdict"], self.VERDICTS)


if __name__ == "__main__":
    unittest.main()
