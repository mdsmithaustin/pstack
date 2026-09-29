#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


def session_slug(workspace: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))


def efforts_by_agent(session_dir: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
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
            entry = result.setdefault(agent_id, {"efforts": [], "per_turn_efforts": [], "models": []})
            entry["efforts"].append(record.get("effort"))
            entry["per_turn_efforts"].append(record.get("perTurnEffort"))
            entry["models"].append((record.get("message") or {}).get("model"))
    return result
