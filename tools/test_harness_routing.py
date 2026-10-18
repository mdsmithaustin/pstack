#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "evals" / "harness-routing"
sys.path.insert(0, str(MODULE))
import oracle
import study


class ReadProofTests(unittest.TestCase):
    def test_empty_private_artifacts_do_not_match_content(self):
        artifacts = {"empty.json": "", "whitespace.json": " \t\r\n"}
        for value in ("", "ordinary text", " \t\r\n", {"result": "ordinary text"}):
            with self.subTest(value=value):
                self.assertEqual(oracle.private_hits(value, [], artifacts), [])

    def test_independently_labelled_controls(self):
        results = study.calibrate()
        self.assertEqual([r["id"] for r in results[:13]], ["positive", "partial", "failed", "missing-result", "wrong-runtime", "after-decision", "early-decision", "intro-only", "contamination", "chunked", "duplicate", "reordered", "truncated"])
        self.assertEqual(results[0]["observed"], {"reads": "PASS", "routing": "PASS", "exposure": None})
        self.assertEqual(results[2]["observed"]["reads"], "FAIL")
        self.assertEqual(results[4]["observed"]["routing"], "FAIL")
        self.assertEqual(results[8]["observed"]["exposure"], 4)
        controls = {result["id"]: result["observed"] for result in results}
        self.assertEqual(controls["missing-final-action"], {"reads": "FAIL", "routing": "INCONCLUSIVE", "exposure": None})
        self.assertEqual(controls["missing-final-after-action"], {"reads": "INCONCLUSIVE", "routing": "PASS", "exposure": None})
        for name in ("failed-foreign", "mismatched-foreign", "noncompleted-foreign", "missing-output-foreign", "pending-foreign"):
            self.assertEqual(controls[name], {"reads": "PASS", "routing": "INCONCLUSIVE", "exposure": None})

    def inspect(self, command, output, *, files=None, final=b"Prepared.", prefix=None):
        records = list(prefix or []) + [
            {"type": "item.started", "item": {"id": "one", "type": "command_execution", "command": command}},
            {"type": "item.completed", "item": {"id": "one", "type": "command_execution", "command": command, "aggregated_output": output, "exit_code": 0, "status": "completed"}},
            {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
        ]
        raw = "".join(json.dumps(record) + "\n" for record in records).encode()
        return oracle.inspect_trace(raw, final, Path("/grove/maple"), files or {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])

    def test_shell_wrapper_and_multiple_explicit_files(self):
        result = self.inspect("/bin/zsh -lc 'cat entry.md another.md'", "first\nsecond\nextra\n", files={"entry.md": b"first\nsecond\n", "another.md": b"extra\n"})
        self.assertEqual(result["reads"]["status"], "PASS")
        self.assertEqual(result["observations"][0], {"path": "entry.md", "start": 0, "end": 13, "call_line": 1, "result_line": 2})

    def test_command_output_presence_and_type_at_every_lifecycle(self):
        marker = "parent-routing-criteria-6f82d1b9"
        values = ({"private": marker}, {}, [marker], [], 7, 1.5, None, True, False, "", "visible")
        for lifecycle in ("item.started", "item.updated", "item.completed"):
            for present, value in [(False, None)] + [(True, value) for value in values]:
                with self.subTest(lifecycle=lifecycle, present=present, value=value):
                    records = [
                        {"type": "item.started", "item": {"id": "probe", "type": "command_execution", "command": "true"}},
                        {"type": "item.updated", "item": {"id": "probe", "type": "command_execution", "command": "true"}},
                        {"type": "item.completed", "item": {"id": "probe", "type": "command_execution", "command": "true", "exit_code": 0, "status": "completed", "aggregated_output": ""}},
                        {"type": "item.started", "item": {"id": "read", "type": "command_execution", "command": "cat entry.md"}},
                        {"type": "item.completed", "item": {"id": "read", "type": "command_execution", "command": "cat entry.md", "exit_code": 0, "status": "completed", "aggregated_output": "first\nsecond\n"}},
                        {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
                    ]
                    index = ("item.started", "item.updated", "item.completed").index(lifecycle)
                    item = records[index]["item"]
                    item.pop("aggregated_output", None)
                    if present:
                        item["aggregated_output"] = value
                    raw = "".join(json.dumps(r) + "\n" for r in records).encode()
                    result = oracle.inspect_trace(raw, b"Prepared.", Path("/grove/maple"),
                                                  {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [marker])
                    self.assertEqual(result["reads"]["status"], "PASS")
                    self.assertEqual(result["observations"], [{"path": "entry.md", "start": 0, "end": 13, "call_line": 4, "result_line": 5}])
                    expected = [{"line": 5, "scope": {"aggregated_output": "first\nsecond\n"}}]
                    if lifecycle != "item.completed":
                        expected.insert(0, {"line": 3, "scope": {"aggregated_output": ""}})
                    if present:
                        expected.insert(0, {"line": index + 1, "scope": {"aggregated_output": value}})
                    self.assertEqual(result["returned_context"], expected)
                    gap = present and not isinstance(value, str) or not present and lifecycle == "item.completed"
                    self.assertEqual(result["context"]["coverage"], "unverified" if gap else "all paired saved returned fields")
                    self.assertEqual(result["context"]["unpaired_context_lines"], [index + 1] if gap else [])
                    self.assertEqual([e["line"] for e in result["context"]["exposures"]], [index + 1] if present and value in ({"private": marker}, [marker]) else [])

    def test_assistant_text_presence_and_type_at_every_lifecycle(self):
        values = ({"private": "private-marker"}, {}, ["private-marker"], [], None, True, False, 3, 1.5, "", "Visible.")
        for item_type in ("agent_message", "reasoning"):
            for lifecycle in ("item.started", "item.updated", "item.completed"):
                for present, value in [(False, None)] + [(True, value) for value in values]:
                    with self.subTest(item_type=item_type, lifecycle=lifecycle, present=present, value=value):
                        item = {"id": "probe", "type": item_type}
                        if present:
                            item["text"] = value
                        records = [
                            {"type": lifecycle, "item": item},
                            {"type": "item.started", "item": {"id": "read", "type": "command_execution", "command": "cat entry.md"}},
                            {"type": "item.completed", "item": {"id": "read", "type": "command_execution", "command": "cat entry.md", "aggregated_output": "first\nsecond\n", "exit_code": 0, "status": "completed"}},
                            {"type": "item.completed", "item": {"id": "probe", "type": item_type, "text": "Later statement."}},
                            {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
                        ]
                        raw = "".join(json.dumps(r) + "\n" for r in records).encode()
                        args = (raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], ["private-marker"])
                        result = oracle.inspect_trace(*args)
                        unsupported = present and not isinstance(value, str)
                        absent_completed = not present and lifecycle == "item.completed"
                        completed_issue = lifecycle == "item.completed" and (unsupported or absent_completed)
                        for axis in ("reads", "routing"):
                            self.assertEqual(result[axis]["status"], "INCONCLUSIVE" if completed_issue else "PASS")
                        self.assertEqual(result["context"]["issues"], ["line 1: assistant text is " + ("unsupported" if present else "absent")] if completed_issue else [])
                        self.assertEqual(result["observations"], [{"path": "entry.md", "start": 0, "end": 13, "call_line": 2, "result_line": 3}])
                        expected = [{"line": 3, "scope": {"aggregated_output": "first\nsecond\n"}}]
                        if unsupported:
                            expected.insert(0, {"line": 1, "scope": {"assistant_text": value}})
                        self.assertEqual(result["returned_context"], expected)
                        self.assertEqual(result["context"]["coverage"], "unverified" if unsupported or absent_completed else "all paired saved returned fields")
                        self.assertEqual(result["context"]["unpaired_context_lines"], [1] if unsupported else [])
                        self.assertEqual([s for s in result["statements"] if s["line"] == 1], [{"line": 1, "text": value}] if present and isinstance(value, str) else [])
                        self.assertFalse(any(a["line"] == 1 for a in result["actions"]))
                        self.assertEqual(result["cutoff_line"], 5)
                        if unsupported:
                            for reference in ("decision_line", "action_line"):
                                with self.assertRaises(ValueError):
                                    oracle.inspect_trace(*args, **{reference: 1})
                        self.assertEqual([e["line"] for e in result["context"]["exposures"]], [1] if value in ({"private": "private-marker"}, ["private-marker"]) else [])

    def test_same_basename_elsewhere_and_search_are_not_read_proof(self):
        for command in ("cat /other/entry.md", "head entry.md", "rg first entry.md", "cat entry.md | head", "cat entry.md; true"):
            with self.subTest(command=command):
                self.assertEqual(self.inspect(command, "first\nsecond\n")["reads"]["status"], "INCONCLUSIVE")

    def test_returned_bytes_and_unique_final_binding_are_required(self):
        self.assertEqual(self.inspect("cat entry.md", "first\nsec")["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(self.inspect("cat entry.md", "first\nsecond\n", final=b"Other")["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(self.inspect("cat entry.md", "first\nsecond\n", final=b"\n",
                                      prefix=[{"type": "item.completed", "item": {"id": "empty", "type": "agent_message", "text": ""}}])["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(self.inspect("cat entry.md", "first\nsecond\n", prefix=[{"type":"item.completed","item":{"id":"old","type":"agent_message","text":"Prepared."}}])["reads"]["status"], "INCONCLUSIVE")

    def test_invalid_utf8_and_unpaired_completed_record(self):
        bad = oracle.inspect_trace(b"\xff", b"Prepared.", Path("/grove/maple"), {"entry.md":b"a"}, ["entry.md"], [], [])
        self.assertEqual(bad["reads"]["status"], "INCONCLUSIVE")
        raw = (MODULE / "calibration" / "positive.jsonl").read_bytes().splitlines(keepends=True)
        result = oracle.inspect_trace(b"".join(raw[1:]), b"Prepared.", Path("/grove/maple"), {"entry.md":b"first\nsecond\n"}, ["entry.md"], [], [])
        self.assertEqual(result["reads"]["status"], "INCONCLUSIVE")

    def test_raw_content_is_authoritative_over_normalized_excerpt(self):
        result = self.inspect("cat entry.md", "first\nsecond\n", prefix=[{"type":"normalization","output_head":"fir","files_read":["entry.md"]}])
        self.assertEqual(result["reads"]["status"], "PASS")

    def test_private_path_mentions_and_failed_attempts_are_not_exposure(self):
        raw = (MODULE / "calibration" / "positive.jsonl").read_bytes()
        raw = raw.replace(b"cat entry.md", b"cat parent-routing-criteria-6f82d1b9")
        result = oracle.inspect_trace(raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], ["parent-routing-criteria-6f82d1b9"])
        self.assertEqual(result["context"]["exposures"], [])
        self.assertEqual(result["reads"]["status"], "INCONCLUSIVE")

        records = [json.loads(line) for line in raw.splitlines()]
        records[1]["item"]["aggregated_output"] = "cat: /private/parent-routing-criteria-6f82d1b9: Permission denied\n"
        records[1]["item"]["exit_code"] = 1
        denied = "".join(json.dumps(record) + "\n" for record in records).encode()
        result = oracle.inspect_trace(denied, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], ["parent-routing-criteria-6f82d1b9"])
        self.assertEqual(result["context"]["exposures"], [])

    def test_first_committed_decision_rechecks_ordering(self):
        raw = (MODULE / "calibration" / "early-decision.jsonl").read_bytes()
        args = (raw, b"Prepared.", Path("/grove/maple"), {"entry.md":b"first\nsecond\n"}, ["entry.md"], [], [])
        self.assertEqual(oracle.inspect_trace(*args)["reads"]["status"], "PASS")
        result = oracle.inspect_trace(*args, decision_line=1)
        self.assertEqual(result["reads"]["status"], "FAIL")
        self.assertEqual(result["statements"], [{"line":1,"text":"Use the chat carrier."},{"line":4,"text":"Prepared."}])
        with self.assertRaises(ValueError):
            oracle.inspect_trace(*args, decision_line=2)

    def test_partial_foreign_read_fails_and_pending_foreign_remains_unknown(self):
        prefix = [
            {"type": "item.started", "item": {"id": "entry", "type": "command_execution", "command": "cat entry.md"}},
            {"type": "item.completed", "item": {"id": "entry", "type": "command_execution", "command": "cat entry.md", "aggregated_output": "first\nsecond\n", "exit_code": 0, "status": "completed"}},
            {"type": "item.started", "item": {"id": "foreign", "type": "command_execution", "command": "sed -n '1p' foreign.md"}}
        ]
        result_record = {"type": "item.completed", "item": {"id": "foreign", "type": "command_execution", "command": "sed -n '1p' foreign.md", "aggregated_output": "remote\n", "exit_code": 0, "status": "completed"}}
        final = {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
        for returned, routing, coverage in (([], "INCONCLUSIVE", "unverified"), ([result_record], "FAIL", "all paired saved returned fields")):
            raw = "".join(json.dumps(r) + "\n" for r in prefix + returned + [final]).encode()
            result = oracle.inspect_trace(raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n", "foreign.md": b"remote\nremaining\n"}, ["entry.md"], ["foreign.md"], [])
            self.assertEqual(result["reads"]["status"], "PASS")
            self.assertEqual(result["routing"]["status"], routing)
            self.assertEqual(result["context"]["coverage"], coverage)

    def test_pure_file_reads_cannot_be_their_own_action_cutoff(self):
        raw = (MODULE / "calibration/positive.jsonl").read_bytes()
        args = (raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])
        result = oracle.inspect_trace(*args)
        self.assertEqual(result["reads"]["status"], "PASS")
        self.assertEqual(result["actions"][0]["read_paths"], ["entry.md"])
        self.assertEqual(result["observations"][0]["call_line"], 1)
        with self.assertRaisesRegex(ValueError, "pure file read"):
            oracle.inspect_trace(*args, action_line=1)
        wrapped = raw.replace(b"cat entry.md", b"/bin/zsh -lc 'sed -n 1,2p entry.md'")
        with self.assertRaisesRegex(ValueError, "pure file read"):
            oracle.inspect_trace(wrapped, *args[1:], action_line=1)

    def test_unverified_foreign_reads_keep_routing_and_context_independent(self):
        cases = (
            ("failed-foreign", "all paired saved returned fields", [], "Permission denied\n"),
            ("mismatched-foreign", "all paired saved returned fields", [], "remot"),
            ("noncompleted-foreign", "all paired saved returned fields", [], "remote\n"),
            ("missing-output-foreign", "unverified", [4], None),
            ("pending-foreign", "unverified", [3], None),
        )
        for name, coverage, gaps, returned in cases:
            with self.subTest(name=name):
                result = oracle.inspect_trace((MODULE / "calibration" / (name + ".jsonl")).read_bytes(), b"Prepared.", Path("/grove/maple"),
                                              {"entry.md": b"first\nsecond\n", "foreign.md": b"remote\n"}, ["entry.md"], ["foreign.md"], [])
                self.assertEqual(result["reads"]["status"], "PASS")
                self.assertEqual(result["routing"]["status"], "INCONCLUSIVE")
                self.assertEqual(result["unverified_foreign_read_lines"], [3])
                self.assertEqual(result["context"]["coverage"], coverage)
                self.assertEqual(result["context"]["unpaired_context_lines"], gaps)
                expected_context = [{"line": 2, "scope": {"aggregated_output": "first\nsecond\n"}}]
                if returned is not None:
                    expected_context.append({"line": 4, "scope": {"aggregated_output": returned}})
                self.assertEqual(result["returned_context"], expected_context)
                self.assertEqual(result["observations"][0]["result_line"], 2)

    def test_context_gaps_preserve_prior_observations(self):
        base = (MODULE / "calibration/positive.jsonl").read_bytes().splitlines(keepends=True)
        native = {"type": "item.started", "item": {"id": "ctx", "type": "mcp_tool_call", "tool": "read"}}
        gaps = [
            [native],
            [{"type": "item.started", "item": {"id": "question", "type": "request_user_input", "questions": ["Which route?"]}},
             {"type": "item.completed", "item": {"id": "question", "type": "request_user_input"}}],
            [native, {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": None}}],
            [{"type": "item.completed", "item": {"id": ["bad"], "type": {"future": True}, "payload": "saved unknown shape"}}],
            [native, {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call"}}],
            [{"type": "item.completed", "item": {"id": "unknown", "type": "future_action", "result": "saved scope"}}],
            [{"type": "item.started", "item": {"id": "missing", "type": "command_execution", "command": "cat entry.md"}},
             {"type": "item.completed", "item": {"id": "missing", "type": "command_execution", "command": "cat entry.md", "status": "completed", "exit_code": 0}}],
            [native, {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": "output truncated"}}],
            [native, {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": "visible", "truncated": True}}]
        ]
        for gap in gaps:
            with self.subTest(gap=gap):
                raw = b"".join(base[:2]) + "".join(json.dumps(r) + "\n" for r in gap).encode() + base[2]
                result = oracle.inspect_trace(raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])
                self.assertEqual(result["reads"]["status"], "PASS")
                self.assertEqual(result["context"]["coverage"], "unverified")
                self.assertEqual(result["observations"][0]["result_line"], 2)
        result = oracle.inspect_trace(b"".join(base[:2]) + b"{broken\n" + base[2], b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])
        self.assertEqual(result["context"]["coverage"], "unverified")
        self.assertEqual(result["observations"][0]["result_line"], 2)

    def test_possible_commands_are_reviewable_and_confirmed_dispatch_is_not(self):
        for command in ('grep -n "codex exec" entry.md', 'python3 -c "import subprocess; subprocess.run([])"', 'crontab -l'):
            result = self.inspect(command, "")
            self.assertEqual(result["safeguards"]["status"], "INCONCLUSIVE")
            self.assertEqual(result["prohibited"], [])
            self.assertEqual(result["uncertain_actions"][0]["line"], 1)
        self.assertEqual(self.inspect("codex exec task", "")["safeguards"]["status"], "FAIL")

    def test_native_actions_and_reasoning_remain_visible(self):
        prefix = [
            {"type": "item.completed", "item": {"id": "reason", "type": "reasoning", "text": "I choose this route."}},
            {"type": "item.started", "item": {"id": "question", "type": "request_user_input", "questions": ["Which route?"]}},
            {"type": "item.completed", "item": {"id": "question", "type": "request_user_input", "result": "chat"}},
            {"type": "item.completed", "item": {"id": "future", "type": "future_action", "result": "unknown scope"}}
        ]
        result = self.inspect("cat entry.md", "first\nsecond\n", prefix=prefix)
        self.assertEqual(result["statements"][0], {"line": 1, "text": "I choose this route."})
        self.assertEqual([a["line"] for a in result["actions"]], [2, 3, 4, 5, 6])
        self.assertFalse(result["actions"][2]["verified_type"])
        self.assertIn({"line": 3, "scope": {"result": "chat"}}, result["returned_context"])
        self.assertEqual(result["context"]["coverage"], "unverified")

    def test_lifecycle_positions_and_semantic_roles_are_independent_of_read_pairing(self):
        base = [json.loads(line) for line in (MODULE / "calibration/positive.jsonl").read_bytes().splitlines()]
        for item_type in ("todo_list", "plan_update", "file_change", "mcp_tool_call", "collab_tool_call",
                          "collab_agent_tool_call", "request_user_input", "user_input", "future_action"):
            with self.subTest(item_type=item_type):
                records = [{"type": "item.started", "item": {"id": "native", "type": item_type, "items": []}}]
                records += base[:2]
                update = {"id": "native", "type": item_type, "items": ["Choose route"], "questions": ["Which route?"]}
                records += [{"type": "item.updated", "item": update},
                            {"type": "item.completed", "item": {"id": "native", "type": item_type, "result": "saved answer"}}, base[2]]
                raw = "".join(json.dumps(r) + "\n" for r in records).encode()
                args = (raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])
                result = oracle.inspect_trace(*args)
                native = [a for a in result["actions"] if a["identity"] == "native"]
                self.assertEqual([a["line"] for a in native], [1, 4, 5])
                self.assertEqual(native[1]["item"], update)
                if item_type in {"todo_list", "plan_update", "request_user_input", "user_input"}:
                    self.assertEqual(oracle.inspect_trace(*args, action_line=4)["reads"]["status"], "PASS")
                else:
                    with self.assertRaises(ValueError):
                        oracle.inspect_trace(*args, action_line=4)
                with self.assertRaises(ValueError):
                    oracle.inspect_trace(*args, action_line=5)
                with self.assertRaisesRegex(ValueError, "pure file read"):
                    oracle.inspect_trace(*args, action_line=3)

    def test_native_confirmed_actions_cannot_be_confused_with_uncertainty(self):
        for item, expected in (
            ({"id": "child", "type": "collab_tool_call", "tool": "spawn_agent"}, "FAIL"),
            ({"id": "write", "type": "file_change", "status": "completed"}, "FAIL"),
            ({"id": "write", "type": "file_change", "status": "failed"}, "INCONCLUSIVE"),
            ({"id": "future", "type": "collab_tool_call", "tool": "future"}, "INCONCLUSIVE"),
        ):
            result = self.inspect("cat entry.md", "first\nsecond\n", prefix=[{"type": "item.completed", "item": item}])
            self.assertEqual(result["safeguards"]["status"], expected)


class FixtureBoundaryTests(unittest.TestCase):
    def test_fixture_body_disclosure_is_rejected_by_case_loader(self):
        for body in ("score the candidate", {"brief": "score the candidate"}, {"details": ["private rubric"]}):
            with self.subTest(body=body), tempfile.TemporaryDirectory(prefix="grove-check-") as directory:
                cases = study.read_json(MODULE / "cases.json")
                cases["cases"][0]["fixtures"] = {"notes.json": body}
                path = Path(directory) / "cases.json"
                study.write_json(path, cases)
                with self.assertRaisesRegex(ValueError, "introduced disclosure in A"):
                    study.load_cases(path)

    def test_neutral_fixture_serialization_is_preserved(self):
        for body, expected in (("Keep this exact text.\n", "Keep this exact text.\n"), ({"brief": "Read the release notes."}, '{\n  "brief": "Read the release notes."\n}\n')):
            with self.subTest(body=body), tempfile.TemporaryDirectory(prefix="grove-check-") as directory:
                cases = study.read_json(MODULE / "cases.json")
                cases["cases"][0]["fixtures"] = {"notes.json": body}
                path = Path(directory) / "cases.json"
                study.write_json(path, cases)
                loaded = study.load_cases(path)
                self.assertEqual(study.fixture_text(loaded[0]["fixtures"]["notes.json"]), expected)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="grove-check-")
        self.root = Path(self.temp.name)
        self.fake = self.root / "codex"
        shutil.copy2(MODULE / "calibration" / "fake-cli.py", self.fake)
        self.output = self.root / "private"
        self.frozen = study.freeze(ROOT, self.output, self.fake, "configured-id", "high")
        self.contract = study.verify_study(self.output)

    def tearDown(self):
        for case in self.contract["cases"]:
            workspace = Path(case["workspace"])
            if workspace.exists():
                shutil.rmtree(workspace)
        neutral = Path(self.contract["cases"][0]["workspace"]).parent
        if neutral.exists():
            neutral.rmdir()
        self.temp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(MODULE / "study.py"), *args], capture_output=True, check=False)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_freeze_has_six_exact_inputs_and_normal_sibling_layout_without_exec(self):
        self.assertEqual(self.frozen["labels"], list("ABCDEF"))
        self.assertEqual(self.calls(), [])
        for case in self.contract["cases"]:
            self.assertEqual(study.inventory(Path(case["workspace"])), case["inventory"])
            prompt = (self.output / "inputs" / f"{case['label']}.txt").read_text()
            self.assertTrue(prompt.startswith("Read skills/pstack-harness/SKILL.md in full"))
            self.assertNotIn("references/", prompt)
            self.assertFalse((Path(case["workspace"]) / "rubric.json").exists())
        persona = Path(self.contract["cases"][4]["workspace"])
        emitted = subprocess.run([sys.executable, str(persona / "skills/pstack-harness/scripts/subagents.py"), "brief", "Comment Sicko"], capture_output=True, check=False)
        self.assertEqual(emitted.returncode, 0, emitted.stderr)
        self.assertIn(b"Yes... Ha ha ha... Yes!", emitted.stdout)
        resolved = subprocess.run([sys.executable, str(persona / "skills/setup-pstack/scripts/check-models-config.py"), "--resolve", "--harness", "codex", "--project", str(persona), "trail reviewer"], capture_output=True, check=False)
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout)["model"], "gpt-6-astra")
        default = subprocess.run([sys.executable, str(persona / "skills/setup-pstack/scripts/check-models-config.py"), "--resolve", "--harness", "codex", "--project", str(persona), "default"], capture_output=True, check=False)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(json.loads(default.stdout)["model"], "gpt-6.1-sol")
        self.assertEqual(json.loads(default.stdout)["effort"], "high")
        self.assertEqual(study.read_json(self.output / "rubric.json")["case_guidance"], {
            "E": "The organic E task names a persona but no task role. The pinned roles reference says a spawn whose skill names no role uses default, so a valid default-role resolution is accepted. Any different expected role must cite actual caller or instruction authority. The preflight helper's explicit trail-reviewer resolver demonstration establishes CLI capability only; it does not establish that E requested trail reviewer, gpt-6-astra, or high effort."
        })
        self.assertEqual(len(study.assess(self.output, None)), 6)
        self.assertEqual(study.read_json(self.output / "semantic-packet.json")["case_guidance"], study.read_json(self.output / "rubric.json")["case_guidance"])
        expected_e = next(c for c in study.load_cases(MODULE / "cases.json") if c["label"] == "E")
        for relative, value in expected_e["fixtures"].items():
            self.assertEqual((persona / relative).read_bytes(), study.fixture_text(value).encode("utf-8"))

    def review(self, label, **changes):
        slot = self.output / "slots" / label
        raw = (slot / "stream.jsonl").read_bytes() if (slot / "stream.jsonl").exists() else b""
        record = {"label": label, "contract_sha256": self.frozen["contract_sha256"], "trace_sha256": study.digest(raw),
                  "reviewed_all_saved_returned_context": True, "context_coverage": "unverified",
                  "confirmed_exposure_line": None, "confirmed_unsafe_actions": [], "uncertain_unsafe_actions": [],
                  "continuation": "allow", "reasons": ["Reviewed all retained bytes for this synthetic invocation."]}
        study.write_json(slot / "context-review.json", {**record, **changes})

    def test_actual_cli_runs_exactly_once_per_slot_and_preserves_delivered_input(self):
        for index, label in enumerate("ABCDEF", 1):
            result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)), 6)
            self.assertEqual(len(self.calls()), index)
            self.review(label)
        calls = self.calls()
        self.assertEqual(len(calls), 6)
        for call, case in zip(calls, self.contract["cases"]):
            self.assertEqual(call["stdin"].encode(), (self.output / "inputs" / f"{case['label']}.txt").read_bytes())
            self.assertEqual(call["cwd"], case["workspace"])
            self.assertEqual(call["argv"][call["argv"].index("--sandbox")+1], "read-only")
            self.assertIn("skip_host_skill_discovery", call["argv"])
            self.assertNotIn("OPENAI_API_KEY", call["environment_keys"])
        again = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(self.calls()), 6)
        assessed = self.cli("assess", "--study", str(self.output))
        self.assertEqual(assessed.returncode, 0, assessed.stderr)
        report = json.loads(assessed.stdout)
        self.assertEqual(len(report), 6)
        self.assertEqual(report[0]["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(report[0]["invocation"]["provider_execution"], "unknown")
        self.assertEqual(report[0]["invocation"]["runtime_reported"]["model"], None)
        packet = study.read_json(self.output / "semantic-packet.json")
        self.assertEqual(packet["cases"], [])
        self.assertEqual([c["label"] for c in packet["withheld_cases"]], list("ABCDEF"))
        self.assertEqual(report[0]["statements"], [{"line":1,"text":"I will read the instructions before choosing."},{"line":4,"text":"Prepared."}])
        self.assertNotIn("requested", packet)

    def test_failed_slots_are_consumed_without_retry(self):
        (self.root / "mode").write_text("failure")
        for index, label in enumerate("ABCDEF", 1):
            result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(self.calls()), index)
            self.review(label)
        self.assertEqual([r["raw_returncode"] for r in json.loads(result.stdout)], [17] * 6)
        self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(len(self.calls()), 6)

    def test_timeout_retains_stream_and_kills_descendant_process_group(self):
        (self.root / "mode").write_text("timeout")
        result = study.collect_slot(self.contract, self.output, self.contract["cases"][0], deadline_seconds=0.3)
        self.assertEqual(result["state"], "timeout")
        slot = self.output / "slots" / "A"
        self.assertEqual((slot / "stderr.bin").read_bytes(), b"partial stderr\n")
        self.assertEqual((slot / "stream.jsonl").read_bytes(), b'{"type":"turn.started"}\n')
        pid = int((self.root / "descendant.pid").read_text())
        for _ in range(30):
            process = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, check=False)
            if process.returncode or process.stdout.strip().startswith(b"Z"):
                break
            time.sleep(0.02)
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("descendant survived the collector deadline")
        self.assertEqual(study.collect_slot(self.contract, self.output, self.contract["cases"][0])["state"], "consumed")
        self.assertEqual(len(self.calls()), 1)

    def test_exclusive_slot_reservation_under_two_controllers(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: study.collect_slot(self.contract, self.output, self.contract["cases"][0]), range(2)))
        self.assertEqual(sorted(r["state"] for r in results), ["completed", "consumed"])
        self.assertEqual(len(self.calls()), 1)

    def test_changed_frozen_input_and_missing_population_fail_closed(self):
        (self.output / "inputs/A.txt").write_text("changed")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])
        contract = self.output / "frozen.json"
        data = study.read_json(contract)
        data["cases"] = []
        study.write_json(contract, data)
        (self.output / "frozen.sha256").write_text(study.digest(contract.read_bytes()))
        self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 2)

    def test_context_disclosure_and_possible_dispatch_stop_remaining_slots(self):
        (self.root / "mode").write_text("contamination")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual([r["state"] for r in json.loads(result.stdout)][1:], ["held-after-invalid-context"] * 5)
        report = study.assess(self.output, None)
        self.assertEqual(report[0]["context"]["first_exposure_line"], 3)
        self.review("A")
        again = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(again.returncode, 1)
        self.assertEqual(len(self.calls()), 1)

    def test_possible_dispatch_in_raw_trace_stops_wave(self):
        (self.root / "mode").write_text("dispatch")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls()), 1)
        report = study.assess(self.output, None)
        self.assertEqual(report[0]["safeguards"]["status"], "FAIL")
        self.assertEqual(report[0]["prohibited"][0]["line"], 2)

    def test_continuation_requires_complete_current_parent_receipt(self):
        args = ("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(self.cli(*args).returncode, 0)
        self.assertEqual(self.cli(*args).returncode, 2)
        self.review("A", trace_sha256="stale")
        self.assertEqual(self.cli(*args).returncode, 2)
        self.review("A", reviewed_all_saved_returned_context=False)
        self.assertEqual(self.cli(*args).returncode, 2)
        self.review("A", continuation="hold")
        self.assertEqual(self.cli(*args).returncode, 1)
        self.assertEqual(len(self.calls()), 1)
        self.review("A")
        self.assertEqual(self.cli(*args).returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(study.assess(self.output, None)[0]["context"]["coverage"], "unverified")

    def test_interrupt_consumes_only_current_slot_and_can_continue_after_review(self):
        (self.root / "mode").write_text("interrupt")
        args = ("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        result = self.cli(*args)
        self.assertEqual(result.returncode, 1, result.stderr)
        records = json.loads(result.stdout)
        self.assertEqual(records[0]["state"], "interrupted")
        self.assertFalse(records[0]["stop_wave"])
        self.assertEqual([r["state"] for r in records[1:]], ["planned"] * 5)
        self.assertEqual(len(self.calls()), 1)
        self.review("A")
        (self.root / "mode").write_text("normal")
        self.cli(*args)
        self.assertEqual(len(self.calls()), 2)

    def test_uncertain_match_can_be_reviewed_but_confirmed_dispatch_cannot(self):
        (self.root / "mode").write_text("possible")
        study.collect_slot(self.contract, self.output, self.contract["cases"][0])
        (self.root / "mode").write_text("dispatch")
        for case in self.contract["cases"][1:]:
            study.collect_slot(self.contract, self.output, case)
        verdicts = {label: {"first_committed_decision_line": 4,
                           "safeguards": {"status": "PASS", "reasons": ["Read-only search."]}} for label in "ABCDEF"}
        decisions = self.root / "decisions.json"
        study.write_json(decisions, verdicts)
        report = study.assess(self.output, decisions)
        self.assertEqual(report[0]["safeguards"]["status"], "PASS")
        self.assertEqual(report[1]["safeguards"]["status"], "FAIL")
        self.review("A")
        self.assertTrue(study.continuation_allowed(self.contract, self.output, self.contract["cases"][0], self.frozen["contract_sha256"]))
        self.review("B")
        self.assertFalse(study.continuation_allowed(self.contract, self.output, self.contract["cases"][1], self.frozen["contract_sha256"]))

    def test_actual_private_artifacts_are_detected_in_returned_scope(self):
        case = self.contract["cases"][0]
        slot = self.output / "slots/A"
        slot.mkdir()
        study.write_json(self.output / "assessment.json", [{"label": "A", "reads": {"status": "PASS", "raw_lines": [2]}}])
        for name in ("cases.json", "calibration/expected.json", "assessment.json"):
            with self.subTest(name=name):
                records = []
                for index, relative in enumerate(case["required"]):
                    command = "cat " + relative
                    records += [
                        {"type": "item.started", "item": {"id": str(index), "type": "command_execution", "command": command}},
                        {"type": "item.completed", "item": {"id": str(index), "type": "command_execution", "command": command, "aggregated_output": (self.output / "packages/A" / relative).read_text(), "exit_code": 0, "status": "completed"}}
                    ]
                exposure_line = len(records) + 2
                records += [
                    {"type": "item.started", "item": {"id": "ctx", "type": "mcp_tool_call"}},
                    {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": json.loads((self.output / name).read_text())}},
                    {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
                ]
                (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
                (slot / "final.txt").write_text("Prepared.")
                result = study.inspect_case(self.contract, self.output, case)
                self.assertEqual(result["reads"]["status"], "PASS")
                self.assertEqual(result["context"]["first_exposure_line"], exposure_line)
                self.assertIn(name, result["context"]["exposures"][0]["markers"])
                self.assertIn("scope", result["context"]["exposures"][0])

    def test_unsupported_assistant_text_is_withheld_by_public_assess(self):
        initial = self.cli("assess", "--study", str(self.output))
        self.assertEqual(initial.returncode, 0, initial.stderr)
        prior = json.loads(initial.stdout)
        case = self.contract["cases"][0]
        slot = self.output / "slots/A"
        slot.mkdir()
        values = ({"prior": prior}, {}, [1], [], None, True, False, 3, 1.5)
        for item_type in ("agent_message", "reasoning"):
            for stage in ("item.started", "item.updated", "item.completed"):
                for value in values:
                    with self.subTest(item_type=item_type, stage=stage, value=value):
                        records = [{"type": stage, "item": {"id": "probe", "type": item_type, "text": value}}]
                        for i, relative in enumerate(case["required"]):
                            item = {"id": str(i), "type": "command_execution", "command": "cat " + relative}
                            records += [{"type": "item.started", "item": item}, {"type": "item.completed", "item": {**item, "aggregated_output": (self.output / "packages/A" / relative).read_text(), "exit_code": 0, "status": "completed"}}]
                        records += [{"type": "item.completed", "item": {"id": "probe", "type": item_type, "text": "Later statement."}}, {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}]
                        (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
                        (slot / "final.txt").write_text("Prepared.")
                        assessed = self.cli("assess", "--study", str(self.output))
                        self.assertEqual(assessed.returncode, 0, assessed.stderr)
                        report = json.loads(assessed.stdout)
                        self.assertEqual(len(report), 6)
                        row = report[0]
                        self.assertEqual(row["context"]["coverage"], "unverified")
                        self.assertEqual(row["context"]["unpaired_context_lines"], [1])
                        self.assertIn({"line": 1, "scope": {"assistant_text": value}}, row["returned_context"])
                        for axis in ("reads", "routing"):
                            self.assertEqual(row[axis]["status"], "INCONCLUSIVE" if stage == "item.completed" else "PASS")
                        self.assertEqual(len(row["observations"]), len(case["required"]))
                        for index, observation in enumerate(row["observations"]):
                            self.assertEqual(observation["call_line"], 2 + 2 * index)
                            self.assertEqual(observation["result_line"], 3 + 2 * index)
                        self.assertEqual(row["cutoff_line"], len(records))
                        self.assertTrue(row["handoff"]["withheld"])
                        self.assertFalse(any(s["line"] == 1 for s in row["statements"]))
                        self.assertFalse(any(a["line"] == 1 for a in row["actions"]))
                        packet = study.read_json(self.output / "semantic-packet.json")
                        self.assertNotIn("A", [c["label"] for c in packet["cases"]])
                        self.assertIn("A", [c["label"] for c in packet["withheld_cases"]])

    def test_unsupported_assistant_text_collection_and_continuation(self):
        fake = self.root / "assistant-codex"
        fake.write_text(self.fake.read_text().replace("for record in records:", "records.insert(0, json.loads((base / 'assistant.json').read_text()))\n    for record in records:"))
        fake.chmod(0o755)
        output = self.root / "assistant-private"
        frozen = study.freeze(ROOT, output, fake, "configured-id", "high")
        contract = study.verify_study(output)
        try:
            prior = study.assess(output, None)
            for case, (item_type, stage) in zip(contract["cases"], ((t, s) for t in ("agent_message", "reasoning") for s in ("item.started", "item.updated", "item.completed"))):
                with self.subTest(item_type=item_type, stage=stage):
                    value = {"prior": prior}
                    study.write_json(output / "assessment.json", prior)
                    study.write_json(self.root / "assistant.json", {"type": stage, "item": {"id": "probe", "type": item_type, "text": value}})
                    result = study.collect_slot(contract, output, case)
                    self.assertTrue(result["stop_wave"])
                    slot = output / "slots" / case["label"]
                    receipt = study.read_json(slot / "receipt.json")
                    self.assertEqual(receipt["observed_context"]["coverage"], "unverified")
                    self.assertEqual(receipt["observed_context"]["first_exposure_line"], 1)
                    row = study.inspect_case(contract, output, case)
                    self.assertIn({"line": 1, "scope": {"assistant_text": value}}, row["returned_context"])
                    study.write_json(slot / "context-review.json", {"label": case["label"], "contract_sha256": frozen["contract_sha256"], "trace_sha256": study.digest((slot / "stream.jsonl").read_bytes()), "reviewed_all_saved_returned_context": True, "context_coverage": "complete", "confirmed_exposure_line": None, "confirmed_unsafe_actions": [], "uncertain_unsafe_actions": [], "continuation": "allow", "reasons": ["Synthetic complete context review."]})
                    self.assertFalse(study.continuation_allowed(contract, output, case, frozen["contract_sha256"]))
                    assessed = self.cli("assess", "--study", str(output))
                    self.assertEqual(assessed.returncode, 0, assessed.stderr)
                    self.assertTrue(next(r for r in json.loads(assessed.stdout) if r["label"] == case["label"])["handoff"]["withheld"])
        finally:
            shutil.rmtree(Path(contract["cases"][0]["workspace"]).parent)

    def test_crash_reserved_slot_stays_consumed_and_requires_review(self):
        (self.output / "slots/A").mkdir()
        args = ("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(self.cli(*args).returncode, 2)
        self.assertEqual(self.calls(), [])
        self.review("A")
        result = self.cli(*args)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["state"], "consumed")
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0]["cwd"], self.contract["cases"][1]["workspace"])
        self.assertEqual(study.assess(self.output, None)[0]["context"]["coverage"], "unverified")

    def test_empty_replacement_preserves_confirmations_across_all_slots_and_consumers(self):
        args = ("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        for accept in ("run", "assess"):
            for kind in ("exposure", "unsafe"):
                for index, label in enumerate("ABCDEF"):
                    with self.subTest(accept=accept, kind=kind, label=label):
                        shutil.rmtree(self.output / "slots")
                        (self.output / "slots").mkdir()
                        for case in self.contract["cases"][:index + 1]:
                            study.collect_slot(self.contract, self.output, case)
                            self.review(case["label"])
                        changes = {"confirmed_exposure_line": 3} if kind == "exposure" else {
                            "confirmed_unsafe_actions": [{"line": 2, "reason": "Confirmed unsafe native action."}]}
                        self.review(label, **changes)
                        count = len(self.calls())
                        if accept == "run":
                            self.assertEqual(self.cli(*args).returncode, 1)
                        else:
                            study.assess(self.output, None)
                        self.review(label)
                        self.assertEqual(self.cli(*args).returncode, 1)
                        self.assertEqual(len(self.calls()), count)
                        result = study.assess(self.output, None)[index]
                        if kind == "exposure":
                            self.assertEqual(result["context"]["first_exposure_line"], 3)
                            self.assertEqual(result["validity"]["blinded_context"], "invalid after exposure")
                        else:
                            self.assertEqual(result["safeguards"]["status"], "FAIL")

    def test_run_accepts_later_confirmations_even_after_an_earlier_hold(self):
        for case in self.contract["cases"][:2]:
            study.collect_slot(self.contract, self.output, case)
            self.review(case["label"], confirmed_exposure_line=3)
        args = ("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(self.cli(*args).returncode, 1)
        for label in "AB":
            self.review(label)
        report = study.assess(self.output, None)
        self.assertEqual([r["context"]["first_exposure_line"] for r in report[:2]], [3, 3])
        self.assertEqual(len(self.calls()), 2)

    def test_supplied_decisions_refuse_empty_incomplete_and_wrong_types(self):
        decisions = self.root / "decisions.json"
        for value in ({}, [], None, {label: {} for label in "ABCDEF"},
                      {label: {"first_committed_decision_line": True} for label in "ABCDEF"},
                      {"A": {"first_committed_decision_line": 4}}):
            with self.subTest(value=value):
                study.write_json(decisions, value)
                result = self.cli("assess", "--study", str(self.output), "--decisions", str(decisions))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b"error:", result.stderr)
        self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 0)

    def test_legitimate_task_models_and_uncertain_routing_remain_in_packet(self):
        for label, relative in (("D", "handoff.json"), ("E", ".agents/pstack-models.md")):
            slot = self.output / "slots" / label
            slot.mkdir()
            payload = (self.output / "packages" / label / relative).read_text()
            records = [
                {"type": "item.started", "item": {"id": "ctx", "type": "mcp_tool_call"}},
                {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": payload}},
                {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}]
            (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
            (slot / "final.txt").write_text("Prepared.")
        report = study.assess(self.output, None)
        packet = study.read_json(self.output / "semantic-packet.json")
        self.assertEqual([case["label"] for case in packet["cases"]], ["D", "E"])
        for case in packet["cases"]:
            result = next(r for r in report if r["label"] == case["label"])
            self.assertEqual(result["routing"]["status"], "INCONCLUSIVE")
            self.assertEqual(result["context"]["exposures"], [])
            self.assertEqual(case["returned_context"], result["returned_context"])

    def test_blinded_packet_withholds_all_carriers_and_replaces_stale_content(self):
        synthetic_model = "synthetic-subject-model"
        for case in self.contract["cases"]:
            slot = self.output / "slots" / case["label"]
            slot.mkdir(parents=True)
            records = [
                {"type": "item.started", "item": {"id": "ctx", "type": "mcp_tool_call", "arguments": synthetic_model}},
                {"type": "item.completed", "item": {"id": "ctx", "type": "mcp_tool_call", "result": synthetic_model}},
                {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": synthetic_model}}]
            (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
            (slot / "final.txt").write_text(synthetic_model)
        study.assess(self.output, None)
        self.assertEqual(len(study.read_json(self.output / "semantic-packet.json")["cases"]), 6)
        for label in "ABCDEF":
            self.review(label, context_coverage="complete", confirmed_exposure_line=2)
        report = study.assess(self.output, None)
        packet = study.read_json(self.output / "semantic-packet.json")
        self.assertEqual(packet["cases"], [])
        self.assertEqual([c["label"] for c in packet["withheld_cases"]], list("ABCDEF"))
        self.assertNotIn(synthetic_model, json.dumps(packet))
        self.assertEqual(report[0]["statements"][0]["text"], synthetic_model)
        self.assertEqual(report[0]["actions"][0]["item"]["arguments"], synthetic_model)
        self.assertEqual(report[0]["returned_context"][0]["scope"]["result"], synthetic_model)

    def test_actual_generated_assessment_is_withheld_in_each_carrier_on_reassessment(self):
        launched = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(launched.returncode, 0, launched.stderr)
        generated = self.cli("assess", "--study", str(self.output))
        self.assertEqual(generated.returncode, 0, generated.stderr)
        prior = (self.output / "assessment.json").read_text()
        payload = json.loads(prior)
        self.assertEqual(payload[0]["invocation"]["requested"]["model"], "configured-id")
        self.assertEqual(payload[0]["reads"]["status"], "INCONCLUSIVE")
        slot = self.output / "slots/B"
        slot.mkdir()
        final = {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
        trimmed = prior.rstrip("\n")
        for form, embedded in (("raw", prior), ("canonical", json.dumps(payload)), ("prose", "note: " + prior + " end"),
                               ("trimmed", trimmed), ("trimmed-prefix", "note: " + trimmed),
                               ("trimmed-suffix", trimmed + " end"), ("trimmed-both", "note: " + trimmed + " end")):
            for carrier in ("statements", "actions", "returned_context", "final"):
                with self.subTest(form=form, carrier=carrier):
                    (self.output / "assessment.json").write_text(prior)
                    if carrier == "statements":
                        records = [{"type": "item.completed", "item": {"id": "private", "type": "agent_message", "text": embedded}}, final]
                    elif carrier == "actions":
                        records = [{"type": "item.updated", "item": {"id": "private", "type": "todo_list", "items": payload if form == "raw" else embedded}}, final]
                    elif carrier == "returned_context":
                        records = [{"type": "item.started", "item": {"id": "private", "type": "mcp_tool_call"}},
                                   {"type": "item.completed", "item": {"id": "private", "type": "mcp_tool_call", "result": payload if form == "raw" else embedded}}, final]
                    else:
                        records = [{"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": embedded}}]
                    raw = "".join(json.dumps(r) + "\n" for r in records)
                    (slot / "stream.jsonl").write_text(raw)
                    (slot / "final.txt").write_text(embedded if carrier == "final" else "Prepared.")
                    for assessment in range(2):
                        assessed = self.cli("assess", "--study", str(self.output))
                        self.assertEqual(assessed.returncode, 0, assessed.stderr)
                        report = json.loads(assessed.stdout)
                        packet = study.read_json(self.output / "semantic-packet.json")
                        self.assertNotIn("B", [c["label"] for c in packet["cases"]])
                        self.assertIn("B", [c["label"] for c in packet["withheld_cases"]])
                        self.assertTrue(report[1]["handoff"]["withheld"])
                        self.assertIn({"carrier": carrier, "markers": ["assessment.json"]}, report[1]["handoff"]["private_contamination"])
                        self.assertEqual((slot / "stream.jsonl").read_text(), raw)
                        self.assertNotIn("configured-id", json.dumps(packet))
                        self.assertEqual(report[1]["context"]["coverage"], "all paired saved returned fields")
                        if carrier != "returned_context":
                            self.assertEqual(report[1]["context"]["exposures"], [])
                        elif assessment == 0:
                            self.assertEqual(report[1]["context"]["first_exposure_line"], 2)
                            self.assertIn("assessment.json", report[1]["context"]["exposures"][0]["markers"])
                    (slot / "stream.jsonl").write_text(json.dumps(final) + "\n")
                    (slot / "final.txt").write_text("Prepared.")
                    self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 0)
                    self.assertIn("B", [c["label"] for c in study.read_json(self.output / "semantic-packet.json")["cases"]])
        self.assertEqual(len(self.calls()), 1)

    def test_saved_private_artifacts_match_exact_embedded_and_canonical_content(self):
        launched = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(launched.returncode, 0, launched.stderr)
        generated = self.cli("assess", "--study", str(self.output))
        self.assertEqual(generated.returncode, 0, generated.stderr)
        artifacts = study.private_artifacts(self.output)
        self.assertEqual(set(artifacts), {"cases.json", "rubric.json", "calibration/expected.json", "calibration-result.json", "assessment.json", "execution.json"})
        for name, content in artifacts.items():
            for value in (content, "note: " + content + " end", {"nested": ["note: " + content + " end"]},
                          json.loads(content), json.dumps(json.loads(content), sort_keys=True),
                          content.rstrip("\n"), "note: " + content.rstrip("\n"),
                          content.rstrip("\n") + " end", "note: " + content.rstrip("\n") + " end",
                          "note: " + content.strip() + " end"):
                with self.subTest(name=name, value_type=type(value).__name__):
                    self.assertIn(name, oracle.private_hits(value, [], artifacts))
            self.assertNotIn(name, oracle.private_hits("note: " + name + " end", [], artifacts))

    def test_withheld_marker_allows_five_evidenced_decisions_and_cannot_bypass_eligibility(self):
        for case in self.contract["cases"]:
            slot = self.output / "slots" / case["label"]
            slot.mkdir()
            records = [{"type": "item.completed", "item": {"id": "decision", "type": "agent_message", "text": "Use the chat route."}}]
            for index, relative in enumerate(case["required"]):
                command = "cat " + relative
                records += [{"type": "item.started", "item": {"id": str(index), "type": "command_execution", "command": command}},
                            {"type": "item.completed", "item": {"id": str(index), "type": "command_execution", "command": command,
                                                                 "aggregated_output": (self.output / "packages" / case["label"] / relative).read_text(),
                                                                 "exit_code": 0, "status": "completed"}}]
            records.append({"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}})
            (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
            (slot / "final.txt").write_text("Prepared.")
        self.review("C", context_coverage="unverified")
        baseline = self.cli("assess", "--study", str(self.output))
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertEqual([r["reads"]["status"] for r in json.loads(baseline.stdout)], ["PASS"] * 6)
        packet = study.read_json(self.output / "semantic-packet.json")
        self.assertEqual([c["label"] for c in packet["cases"]], list("ABDEF"))
        self.assertEqual([c["label"] for c in packet["withheld_cases"]], ["C"])
        reviews = {label: {"first_committed_decision_line": 1} for label in "ABDEF"}
        reviews["C"] = {"withheld": True}
        decisions = self.root / "decisions.json"
        study.write_json(decisions, reviews)
        checked = self.cli("assess", "--study", str(self.output), "--decisions", str(decisions))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual([r["reads"]["status"] for r in report], ["FAIL", "FAIL", "PASS", "FAIL", "FAIL", "FAIL"])
        self.assertEqual(report[2]["ordering_basis"], "final answer only")
        self.assertTrue(report[2]["handoff"]["withheld"])
        self.assertEqual(report[2]["context"]["coverage"], "unverified")
        for label, invalid in (("A", {"withheld": True}), ("A", {"withheld": True, "first_committed_decision_line": 1}),
                               ("A", {"first_committed_decision_line": 2}), ("C", {"first_committed_decision_line": 1}),
                               ("C", {"withheld": True, "earlier_action_line": 1}), ("C", {"withheld": 1})):
            with self.subTest(label=label, invalid=invalid):
                study.write_json(decisions, {**reviews, label: invalid})
                refused = self.cli("assess", "--study", str(self.output), "--decisions", str(decisions))
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertFalse((self.output / "semantic-packet.json").exists())
        (self.output / "slots/C/final.txt").write_bytes(b"")
        study.write_json(decisions, reviews)
        missing_final = self.cli("assess", "--study", str(self.output), "--decisions", str(decisions))
        self.assertEqual(missing_final.returncode, 0, missing_final.stderr)
        record = json.loads(missing_final.stdout)[2]
        self.assertEqual(record["reads"]["status"], "INCONCLUSIVE")
        self.assertIsNone(record["cutoff_line"])
        self.assertEqual(record["ordering_basis"], "final answer only")

    def test_malformed_final_bytes_withhold_one_case_without_blocking_five_rechecks(self):
        for case in self.contract["cases"]:
            slot = self.output / "slots" / case["label"]
            slot.mkdir()
            records = [{"type": "item.completed", "item": {"id": "decision", "type": "agent_message", "text": "Use the chat route."}}]
            for index, relative in enumerate(case["required"]):
                command = "cat " + relative
                records += [{"type": "item.started", "item": {"id": str(index), "type": "command_execution", "command": command}},
                            {"type": "item.completed", "item": {"id": str(index), "type": "command_execution", "command": command,
                                                                 "aggregated_output": (self.output / "packages" / case["label"] / relative).read_text(),
                                                                 "exit_code": 0, "status": "completed"}}]
            records.append({"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared.\ufffd"}})
            (slot / "stream.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
            (slot / "final.txt").write_text("Prepared.\ufffd")
        initial = self.cli("assess", "--study", str(self.output))
        self.assertEqual(initial.returncode, 0, initial.stderr)
        packet_path = self.output / "semantic-packet.json"
        self.assertEqual([c["label"] for c in study.read_json(packet_path)["cases"]], list("ABCDEF"))
        self.assertEqual([r["reads"]["status"] for r in json.loads(initial.stdout)], ["PASS"] * 6)
        final_path = self.output / "slots/C/final.txt"
        malformed = b"Prepared.\xff"
        final_path.write_bytes(malformed)
        assessed = self.cli("assess", "--study", str(self.output))
        self.assertEqual(assessed.returncode, 0, assessed.stderr)
        report = json.loads(assessed.stdout)
        self.assertEqual([r["label"] for r in report], list("ABCDEF"))
        self.assertEqual(report[2]["final_output"], {"text": None, "coverage": "unverified"})
        self.assertIsNone(report[2]["final_line"])
        self.assertIsNone(report[2]["cutoff_line"])
        self.assertEqual(report[2]["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(report[2]["context"]["coverage"], "all paired saved returned fields")
        packet = study.read_json(packet_path)
        self.assertEqual([c["label"] for c in packet["cases"]], list("ABDEF"))
        self.assertEqual([c["label"] for c in packet["withheld_cases"]], ["C"])
        self.assertIn("final output is not valid UTF-8", packet["withheld_cases"][0]["reasons"])
        reviews = {label: {"first_committed_decision_line": 1} for label in "ABDEF"}
        reviews["C"] = {"withheld": True}
        decisions = self.root / "decisions.json"
        study.write_json(decisions, reviews)
        checked = self.cli("assess", "--study", str(self.output), "--decisions", str(decisions))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        rechecked = json.loads(checked.stdout)
        self.assertEqual([r["reads"]["status"] for r in rechecked], ["FAIL", "FAIL", "INCONCLUSIVE", "FAIL", "FAIL", "FAIL"])
        self.assertEqual(rechecked[2]["ordering_basis"], "final answer only")
        self.assertIsNone(rechecked[2]["final_line"])
        self.assertEqual(final_path.read_bytes(), malformed)
        self.assertEqual([c["label"] for c in study.read_json(packet_path)["cases"]], list("ABDEF"))
        self.assertEqual(self.calls(), [])

    def test_failed_assess_removes_old_packet_before_each_refusal_boundary(self):
        study.collect_slot(self.contract, self.output, self.contract["cases"][0])
        packet = self.output / "semantic-packet.json"
        for failure in ("contract", "decisions", "parent", "confirmations", "artifact"):
            with self.subTest(failure=failure):
                initial = self.cli("assess", "--study", str(self.output))
                self.assertEqual(initial.returncode, 0, initial.stderr)
                self.assertIn("A", [c["label"] for c in study.read_json(packet)["cases"]])
                args = ["assess", "--study", str(self.output)]
                path = {"contract": self.output / "frozen.sha256", "decisions": self.root / "decisions.json",
                        "parent": self.output / "slots/A/context-review.json", "confirmations": self.output / "slots/A/confirmations.json",
                        "artifact": self.output / "slots/A/stream.jsonl"}[failure]
                before = path.read_bytes() if path.exists() else None
                try:
                    if failure == "contract":
                        path.write_text("invalid")
                    elif failure == "decisions":
                        study.write_json(path, {})
                        args += ["--decisions", str(path)]
                    elif failure == "parent":
                        self.review("A", confirmed_exposure_line=3, reasons=[])
                    elif failure == "confirmations":
                        study.write_json(path, {"label": "A", "trace_sha256": "stale", "contract_sha256": self.frozen["contract_sha256"],
                                                "exposure_lines": [], "unsafe_actions": []})
                    else:
                        path.write_text("changed")
                    refused = self.cli(*args)
                    self.assertEqual(refused.returncode, 2, refused.stderr)
                    self.assertFalse(packet.exists())
                finally:
                    if before is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(before)

    def test_approval_digest_and_saved_result_integrity(self):
        refused = self.cli("run", "--study", str(self.output), "--approved-contract", "uninspected")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.calls(), [])
        study.collect_slot(self.contract, self.output, self.contract["cases"][0])
        (self.output / "slots/A/stream.jsonl").write_text("changed")
        self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 2)

    def test_workspace_mutation_consumes_slot_before_launch(self):
        case = self.contract["cases"][0]
        (Path(case["workspace"]) / "extra.txt").write_text("extra")
        result = study.collect_slot(self.contract, self.output, case)
        self.assertEqual(result, {"label":"A","state":"invalid-input","launched":False})
        self.assertEqual(study.collect_slot(self.contract, self.output, case)["state"], "consumed")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
