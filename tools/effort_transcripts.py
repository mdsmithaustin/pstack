#!/usr/bin/env python3
"""Pure parsing of Claude Code subagent transcripts for reasoning-effort facts.
It reads only the files the caller names. It makes no network calls, starts no subprocess, and writes nothing."""
from __future__ import annotations

import json
from pathlib import Path


def session_slug(workspace: Path) -> str:
    """Claude Code's project-directory slug: the absolute workspace path with
    every '/' replaced by '-' (per pstack-harness SKILL.md's transcripts hint)."""
    return str(workspace).replace("/", "-")


def efforts_by_agent(session_dir: Path) -> dict[str, dict]:
    """Read every file matching session_dir/subagents/agent-*.jsonl, keep only
    type == "assistant" records, and group them by agentId (falling back to the
    id parsed from the filename, e.g. agent-low.jsonl -> "low", when a record
    has no agentId field).

    Returns {agent_id: {"efforts": [...], "per_turn_efforts": [...], "models": [...]}},
    with one entry per matching assistant record found for that agent, in
    file-then-line order, each list the same length. A record missing
    `effort`, `perTurnEffort`, or `message.model` contributes None at that
    position rather than raising. A session_dir with no subagents directory,
    or one with no matching files, returns {}. A line that fails to parse as
    JSON is skipped, not raised."""
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
