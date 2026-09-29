#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple


class Turn(NamedTuple):
    effort: str | None
    per_turn_effort: str | None
    model: str | None


def session_slug(workspace: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))


def efforts_by_agent(session_dir: Path) -> dict[str, list[Turn]]:
    result: dict[str, list[Turn]] = {}
    subagents_dir = session_dir / "subagents"
    if not subagents_dir.is_dir():
        return result
    for path in sorted(subagents_dir.glob("agent-*.jsonl")):
        fallback_id = path.stem.removeprefix("agent-")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "assistant":
                continue
            agent_id = record.get("agentId") or fallback_id
            turn = Turn(
                effort=record.get("effort"),
                per_turn_effort=record.get("perTurnEffort"),
                model=(record.get("message") or {}).get("model"),
            )
            result.setdefault(agent_id, []).append(turn)
    return result
