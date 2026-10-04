import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import live
from harnesses import claude_code


def session_rows(cwd):
    return [
        {"type": "user", "cwd": cwd, "message": {"role": "user", "content": "/poteto-mode fix it"}},
        {"type": "assistant", "cwd": cwd, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_a", "name": "Read", "input": {"file_path": f"{cwd}/a.py"}},
            {"type": "tool_use", "id": "toolu_b", "name": "Read", "input": {"file_path": f"{cwd}/b.py"}}]}},
        {"type": "user", "cwd": cwd, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_b", "content": "b"},
            {"type": "tool_result", "tool_use_id": "toolu_a", "content": "a"}]}},
    ]


class LoadJsonl(unittest.TestCase):
    def test_literal_unicode_stays_inside_ordered_jsonl_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            for separator in ("\u0085", "\u2028", "\u2029"):
                for newline in ("\n", "\r\n"):
                    with self.subTest(separator=repr(separator), newline=repr(newline)):
                        rows = [
                            {"id": "first", "message": {"content": f"before{separator}after"}},
                            {"id": "last", "message": {"content": "escaped\r\n\t\f\v\u001c\u001d\u001e"}},
                        ]
                        physical_rows = [json.dumps(rows[0], ensure_ascii=False), "", " \t", "{malformed}",
                                         json.dumps(rows[1], ensure_ascii=False)]
                        path.write_bytes(newline.join(physical_rows).encode("utf-8"))
                        self.assertEqual(claude_code.load_jsonl(path), rows)

    def test_invalid_utf8_is_replaced_without_losing_adjacent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_bytes(b'{"id":"first","text":"before\xffafter"}\nnot-json\n{"id":"last","text":"kept"}')
            self.assertEqual(claude_code.load_jsonl(path), [
                {"id": "first", "text": "before\ufffdafter"},
                {"id": "last", "text": "kept"},
            ])

    def test_empty_and_missing_files_keep_their_existing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_bytes(b"")
            self.assertEqual(claude_code.load_jsonl(path), [])
            with self.assertRaises(FileNotFoundError):
                claude_code.load_jsonl(Path(tmp) / "missing.jsonl")


class Harvest(unittest.TestCase):
    def test_claude_tool_events_keep_their_call_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = str(uuid.uuid4())
            case = {"id": "x", "fixture": "tally", "entry": "poteto-mode", "turns": ["fix it"]}
            run = live.Run(root, "claude-code", case, "0" * 40, 60)
            run.project.mkdir(parents=True)
            transcripts = root / "transcripts" / "slug"
            transcripts.mkdir(parents=True)
            rows = session_rows(str(run.project))
            (transcripts / f"{session}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            run.turns = [{"session_id": session, "stream": str(root / "stream-0.jsonl"), "argv": ["claude"], "exit_code": 0, "timed_out": False, "duration_s": 1.0}]
            with patch.object(claude_code, "config_dir", return_value=root / "claude-config"):
                trace = claude_code.harvest(run)
        ids = [(e["kind"], e.get("id")) for e in trace["events"] if e["kind"] in ("tool_call", "tool_result")]
        self.assertEqual(ids, [("tool_call", "toolu_a"), ("tool_call", "toolu_b"),
                               ("tool_result", "toolu_b"), ("tool_result", "toolu_a")])

    def test_literal_unicode_survives_lead_stream_and_child_harvest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = str(uuid.uuid4())
            case = {"id": "x", "fixture": "tally", "entry": "poteto-mode", "turns": ["fix it"]}
            run = live.Run(root, "claude-code", case, "0" * 40, 60)
            run.project.mkdir(parents=True)
            transcripts = root / "transcripts" / "slug"
            children = transcripts / session / "subagents"
            children.mkdir(parents=True)
            prompt = "Review\u2028guide\u0085promises\u2029and evidence."
            child_reply = "persona: poteto-agent\nChild\u2029reply\u0085with\u2028evidence."
            fallback = "Lead\u0085final\u2028reply\u2029from transcript."
            stream_reply = "Stream\u2028final\u2029reply\u0085from result."
            result = "Child\u2029result\u2028with\u0085evidence."
            rows = session_rows(str(run.project)) + [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_child", "name": "Agent", "input": {
                        "subagent_type": "poteto-agent", "model": "sonnet", "prompt": prompt}}]}},
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_child", "content": result}]}},
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": fallback}]}},
            ]
            child = [{"type": "assistant", "perTurnEffort": "high", "message": {
                "role": "assistant", "model": "child-model", "content": [
                    {"type": "text", "text": child_reply},
                    {"type": "tool_use", "id": "toolu_child_read", "name": "Read", "input": {
                        "file_path": str(run.project / "child.py")}}]}}]
            child_path = children / "agent-child.jsonl"
            for path, records in ((transcripts / f"{session}.jsonl", rows), (child_path, child)):
                path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
            (children / "agent-child.meta.json").write_text(json.dumps({
                "toolUseId": "toolu_child", "agentType": "poteto-agent", "model": "sonnet"}))
            stream = root / "stream-0.jsonl"
            init = {"type": "system", "subtype": "init", "claude_code_version": "test-version",
                    "model": "lead-model", "tools": ["Read", "Agent"], "text": "Init\u0085data."}
            run.turns = [{"session_id": session, "stream": str(stream), "argv": ["claude"], "exit_code": 0,
                          "timed_out": False, "duration_s": 1.0}]
            for with_result, expected_reply in ((True, stream_reply), (False, fallback)):
                with self.subTest(with_stream_result=with_result):
                    records = [init] + ([{"type": "result", "result": stream_reply, "total_cost_usd": 0.125}]
                                        if with_result else [])
                    stream.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
                    with patch.object(claude_code, "config_dir", return_value=root / "claude-config"):
                        trace = claude_code.harvest(run)
                    self.assertEqual([(e["seq"], e["kind"], e.get("name"), e.get("id")) for e in trace["events"]], [
                        (0, "user", None, None),
                        (1, "tool_call", "Read", "toolu_a"),
                        (2, "tool_call", "Read", "toolu_b"),
                        (3, "tool_result", "Read", "toolu_b"),
                        (4, "tool_result", "Read", "toolu_a"),
                        (5, "tool_call", "Agent", "toolu_child"),
                        (6, "tool_result", "Agent", "toolu_child"),
                        (7, "text", None, None),
                    ])
                    self.assertEqual(trace["events"][5]["input"]["prompt"], prompt)
                    self.assertEqual(trace["events"][6]["output_head"], result)
                    self.assertEqual(trace["events"][7]["text"], fallback)
                    self.assertEqual(trace["spawns"], [{
                        "seq": 5, "turn": 0, "tool": "Agent", "subagent_type": "poteto-agent", "persona": "poteto-agent",
                        "model": "sonnet", "effort": None, "prompt_head": prompt, "transcript": str(child_path),
                        "observed": {"models": ["child-model"], "efforts": ["high"]},
                        "x_child_first_reply": child_reply, "x_persona_line": "poteto-agent",
                    }])
                    self.assertEqual(trace["x_files_read_by"]["agent-child"], [str(run.project / "child.py")])
                    self.assertEqual(trace["final_reply"], expected_reply)
                    self.assertEqual(trace["x_cost_usd"], 0.125 if with_result else 0)
                    self.assertEqual(trace["cli_version"], "test-version")
                    self.assertEqual(trace["model"], "lead-model")
                    self.assertEqual(trace["x_init_tools"], ["Read", "Agent"])
                    self.assertEqual(trace["x_session_id"], session)


if __name__ == "__main__":
    unittest.main()
