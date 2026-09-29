#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from effort_transcripts import efforts_by_agent, session_slug

FIXTURE_SESSION = Path(__file__).parent / "testdata/effort-transcripts/sample-session"


class EffortsByAgent(unittest.TestCase):
    def test_groups_by_agent_and_filters_non_assistant_records(self):
        result = efforts_by_agent(FIXTURE_SESSION)
        self.assertEqual(set(result), {"low", "high"})
        self.assertEqual(result["low"], {
            "efforts": ["low"],
            "per_turn_efforts": ["low"],
            "models": ["claude-sonnet-4-5-20250929"],
        })
        self.assertEqual(result["high"], {
            "efforts": ["high"],
            "per_turn_efforts": ["high"],
            "models": ["claude-opus-4-5-20250929"],
        })

    def test_missing_subagents_directory_returns_empty(self):
        with tempfile.TemporaryDirectory(prefix="pstack-effort-empty-") as temporary:
            self.assertEqual(efforts_by_agent(Path(temporary)), {})

    def test_tolerates_record_missing_effort_and_model_fields(self):
        with tempfile.TemporaryDirectory(prefix="pstack-effort-sparse-") as temporary:
            session_dir = Path(temporary)
            subagents = session_dir / "subagents"
            subagents.mkdir()
            (subagents / "agent-x.jsonl").write_text('{"type": "assistant", "agentId": "x"}\n', encoding="utf-8")
            self.assertEqual(efforts_by_agent(session_dir), {
                "x": {"efforts": [None], "per_turn_efforts": [None], "models": [None]},
            })

    def test_skips_malformed_json_line(self):
        with tempfile.TemporaryDirectory(prefix="pstack-effort-malformed-") as temporary:
            session_dir = Path(temporary)
            subagents = session_dir / "subagents"
            subagents.mkdir()
            lines = (
                "not json\n"
                '{"type": "assistant", "agentId": "y", "message": {"model": "claude-haiku-4-5"}, '
                '"effort": "medium", "perTurnEffort": "medium"}\n'
            )
            (subagents / "agent-y.jsonl").write_text(lines, encoding="utf-8")
            self.assertEqual(efforts_by_agent(session_dir), {
                "y": {"efforts": ["medium"], "per_turn_efforts": ["medium"], "models": ["claude-haiku-4-5"]},
            })


class SessionSlug(unittest.TestCase):
    def test_replaces_every_slash(self):
        self.assertEqual(session_slug(Path("/Users/me/project")), "-Users-me-project")
        self.assertEqual(session_slug(Path("/a/b/c")), "-a-b-c")

    def test_replaces_every_non_alphanumeric_character(self):
        self.assertEqual(
            session_slug(Path("/private/var/folders/ab/x_y.z/T/tmp_q1")),
            "-private-var-folders-ab-x-y-z-T-tmp-q1",
        )


if __name__ == "__main__":
    unittest.main()
