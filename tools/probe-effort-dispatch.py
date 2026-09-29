#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple
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


class Arm(NamedTuple):
    tag: str
    subagent_type: str
    model: str
    expected_effort: str
    prompt_prefix: str = ""


def arm_prompt(arm: Arm, task: str) -> str:
    if arm.prompt_prefix:
        return f"{arm.prompt_prefix}\n\n{task}"
    return task


def spawn_case(project: Path, session_effort: str, arms: list[Arm]) -> dict:
    session_id = str(uuid.uuid4())
    task = "Reply with the single word OK and nothing else."
    instructions = "; ".join(
        f"one with subagent_type {arm.subagent_type!r}, model {arm.model!r}, description '[{arm.tag}] probe', "
        f"prompt {arm_prompt(arm, task)!r}"
        for arm in arms
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
        turns = efforts.get(agent_id, [])
        last_turn = turns[-1] if turns else None
        observed.append({
            "tag": meta["description"].split("]")[0].lstrip("["),
            "agent_id": agent_id,
            "agent_type": meta["agentType"],
            "model": meta.get("model"),
            "effort": last_turn.effort if last_turn else None,
            "per_turn_effort": last_turn.per_turn_effort if last_turn else None,
        })

    mismatches = []
    for arm in arms:
        row = next((item for item in observed if item["tag"] == arm.tag), None)
        if row is None:
            mismatches.append({"tag": arm.tag, "field": "missing", "expected": arm.subagent_type, "observed": "no spawn"})
            continue
        if row["agent_type"] != arm.subagent_type:
            mismatches.append({"tag": arm.tag, "field": "agent_type", "expected": arm.subagent_type, "observed": row["agent_type"]})
        if row["effort"] != arm.expected_effort:
            mismatches.append({"tag": arm.tag, "field": "effort", "expected": arm.expected_effort, "observed": row["effort"]})
        if row["per_turn_effort"] != arm.expected_effort:
            mismatches.append({"tag": arm.tag, "field": "per_turn_effort", "expected": arm.expected_effort, "observed": row["per_turn_effort"]})
    return {"session_id": session_id, "session_effort": session_effort, "observed": observed, "mismatches": mismatches}


def build_cases(persona_briefing: str) -> list[tuple[str, str, list[Arm]]]:
    return [
        ("dispatch-and-fallback", "high", [
            Arm("wrapper", "pstack-effort-low", "sonnet", "low"),
            Arm("control", "general-purpose", "sonnet", "high"),
        ]),
        ("downward-override", "max", [
            Arm("downward", "pstack-effort-high", "sonnet", "high"),
        ]),
        ("persona-combination", "high", [
            Arm("persona", "pstack-effort-xhigh", "sonnet", "xhigh", persona_briefing),
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
        persona_briefing = subprocess.run(
            [sys.executable, "skills/pstack-harness/scripts/subagents.py", "brief", "poteto-agent"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        for name, session_effort, arms in build_cases(persona_briefing):
            try:
                case = spawn_case(project, session_effort, arms)
            except (OSError, AssertionError, RuntimeError, subprocess.TimeoutExpired) as error:
                report["cases"].append({"name": name, "error": str(error)})
                failed = True
                continue
            report["cases"].append({"name": name, **case})
            if case["mismatches"]:
                failed = True
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        report["cases"].append({"name": "setup", "error": str(error)})
        failed = True

    rendered = json.dumps(report, indent=2) + "\n"
    (run_root / "report.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
