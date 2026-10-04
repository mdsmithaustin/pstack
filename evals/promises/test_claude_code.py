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


if __name__ == "__main__":
    unittest.main()
