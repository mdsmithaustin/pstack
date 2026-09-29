#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from effort_transcripts import efforts_by_agent, session_slug  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, environment: dict[str, str], timeout: int = 180) -> str:
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{command!r} exited {result.returncode}\n{result.stdout}{result.stderr}")
    return result.stdout


def build_project(run_root: Path) -> Path:
    project = run_root / "project"
    project.mkdir(parents=True)
    shutil.copytree(ROOT / "skills", project / ".agents/skills", ignore=shutil.ignore_patterns("__pycache__"))
    script = project / ".agents/skills/pstack-harness/scripts/subagents.py"
    no_tools_environment = dict(os.environ, PATH=str(run_root / "no-git-or-network-tools"))
    run([sys.executable, str(script), "install", "--harness", "claude-code", "--project", str(project)],
        project, no_tools_environment)
    return project


def spawn_case(project: Path, session_effort: str, arms: list[tuple[str, str, str, str]]) -> dict:
    session_id = str(uuid.uuid4())
    instructions = "; ".join(
        f"one with subagent_type {atype!r}, model {model!r}, description '[{tag}] probe', "
        "prompt 'Reply with the single word OK and nothing else.'"
        for tag, atype, model, _ in arms
    )
    prompt = (
        f"Use the Agent tool (Task tool) to spawn exactly {len(arms)} subagents in a single "
        f"message, in parallel: {instructions}. Do not do anything else yourself. "
        "After all of them finish, reply DONE."
    )
    run(
        ["claude", "-p", prompt, "--effort", session_effort, "--model", "sonnet",
         "--output-format", "json", "--allowedTools", "Agent,Task",
         "--session-id", session_id, "--permission-mode", "bypassPermissions"],
        project, dict(os.environ), timeout=300,
    )
    session_dir = Path.home() / ".claude/projects" / session_slug(project) / session_id
    subagents_directory = session_dir / "subagents"
    metas = sorted(subagents_directory.glob("agent-*.meta.json")) if subagents_directory.is_dir() else []
    if not metas:
        raise AssertionError(f"zero spawns found for session {session_id} under {session_dir}")

    efforts = efforts_by_agent(session_dir)
    observed = []
    for meta_path in metas:
        agent_id = meta_path.name.removeprefix("agent-").removesuffix(".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        record = efforts.get(agent_id, {})
        observed.append({
            "tag": meta["description"].split("]")[0].lstrip("["),
            "agent_id": agent_id,
            "agent_type": meta["agentType"],
            "model": meta.get("model"),
            "effort": (record.get("efforts") or [None])[-1],
            "per_turn_effort": (record.get("per_turn_efforts") or [None])[-1],
        })

    mismatches = []
    for tag, expected_type, _, expected_effort in arms:
        row = next((item for item in observed if item["tag"] == tag), None)
        if row is None:
            mismatches.append({"tag": tag, "field": "missing", "expected": expected_type, "observed": "no spawn"})
            continue
        if row["agent_type"] != expected_type:
            mismatches.append({"tag": tag, "field": "agent_type", "expected": expected_type, "observed": row["agent_type"]})
        if row["effort"] != expected_effort:
            mismatches.append({"tag": tag, "field": "effort", "expected": expected_effort, "observed": row["effort"]})
        if row["per_turn_effort"] != expected_effort:
            mismatches.append({"tag": tag, "field": "per_turn_effort", "expected": expected_effort, "observed": row["per_turn_effort"]})
    return {"session_id": session_id, "session_effort": session_effort, "observed": observed, "mismatches": mismatches}


CASES = [
    ("dispatch-and-fallback", "high", [
        ("wrapper", "pstack-effort-low", "sonnet", "low"),
        ("control", "general-purpose", "sonnet", "high"),
    ]),
    ("downward-override", "max", [
        ("downward", "pstack-effort-high", "sonnet", "high"),
    ]),
    ("persona-combination", "high", [
        ("persona", "pstack-effort-xhigh", "sonnet", "xhigh"),
    ]),
]


def main() -> int:
    # resolve(), not absolute(): macOS's tempdir sits under a /var -> /private/var
    # symlink, and Claude Code slugs the resolved cwd, not the raw mkdtemp() path.
    run_root = Path(tempfile.mkdtemp(prefix="pstack-effort-dispatch-probe-")).resolve()
    report = {"run_root": str(run_root), "cases": []}
    failed = False
    try:
        version = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True).stdout.strip()
        report["claude_version"] = version
        project = build_project(run_root)
        for name, session_effort, arms in CASES:
            try:
                case = spawn_case(project, session_effort, arms)
            except (OSError, AssertionError, RuntimeError, subprocess.TimeoutExpired) as error:
                report["cases"].append({"name": name, "error": str(error)})
                failed = True
                continue
            report["cases"].append({"name": name, **case})
            if case["mismatches"]:
                failed = True
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["cases"].append({"name": "setup", "error": str(error)})
        failed = True

    rendered = json.dumps(report, indent=2) + "\n"
    (run_root / "report.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
