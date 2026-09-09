#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], project: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=project, env=environment, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{command!r} exited {result.returncode}\n{result.stdout}{result.stderr}")
    return result.stdout


def probe_case(run_root: Path, copy: bool, source_skills: list[str]) -> dict:
    case = run_root / ("copy" if copy else "symlink")
    project = case / "consumer project"
    project.mkdir(parents=True)
    source = case / "installer source"
    shutil.copytree(ROOT / "skills", source / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    (project / ".hermes").mkdir()
    environment = dict(os.environ, XDG_STATE_HOME=str(case / "installer-state"), DISABLE_TELEMETRY="1", CI="1")
    command = ["npx", "--yes", "skills@1.5.25", "add", str(source), "--skill", "*", "--agent", "claude-code", "codex", "hermes-agent", "--yes"]
    if copy:
        command.append("--copy")
    try:
        output = run(command, project, environment)
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        (case / "install.log").write_text(str(error), encoding="utf-8")
        raise
    (case / "install.log").write_text(output, encoding="utf-8")
    source.rename(case / "source unavailable at runtime")
    environment["PATH"] = str(case / "no-git-or-network-tools")
    installed = project / ".agents/skills"
    actual = sorted(path.parent.name for path in installed.glob("*/SKILL.md"))
    if actual != source_skills:
        raise AssertionError(f"installed skill mismatch: expected {source_skills!r}, found {actual!r}")
    script = installed / "pstack-harness/scripts/subagents.py"
    base = [sys.executable, str(script)]
    check = json.loads(run([*base, "check"], project, environment))
    if check["payload"] != "ready" or check["native_activation"] != "unverified":
        raise AssertionError(f"unexpected payload result: {check}")
    briefs = {}
    for alias, identifier in (("poteto-agent", "poteto-agent"), ("Comment Sicko", "comment-sicko")):
        body = (ROOT / "agents" / (identifier + ".md")).read_text(encoding="utf-8").split("---\n", 2)[2]
        brief = run([*base, "brief", alias], project, environment)
        if body not in brief or str(installed) not in brief or str(source) in brief:
            raise AssertionError(f"incomplete or nonportable briefing for {alias}")
        briefs[identifier] = brief
    for harness, directory, suffix in (("claude-code", ".claude", ".md"), ("codex", ".codex", ".toml")):
        run([*base, "install", "--harness", harness, "--project", str(project)], project, environment)
        run([*base, "check", "--harness", harness, "--project", str(project)], project, environment)
        for identifier, brief in briefs.items():
            text = (project / directory / "agents" / (identifier + suffix)).read_text(encoding="utf-8")
            if harness == "codex":
                parsed = tomllib.loads(text)
                if set(parsed) != {"name", "description", "developer_instructions"} or parsed["developer_instructions"] != brief:
                    raise AssertionError(f"incorrect Codex native persona: {identifier}")
            elif brief not in text or f"name: {identifier}\n" not in text:
                raise AssertionError(f"incorrect Claude native persona: {identifier}")
    for directory in (".claude", ".hermes"):
        linked_harness = project / directory / "skills/pstack-harness"
        if not linked_harness.is_dir() or linked_harness.is_symlink() == copy:
            raise AssertionError(f"unexpected {directory} installation mode")
        logical_script = linked_harness / "scripts/subagents.py"
        brief = run([sys.executable, str(logical_script), "brief", "poteto-agent"], project, environment)
        if str(project / directory / "skills/poteto-mode/SKILL.md") not in brief:
            raise AssertionError(f"{directory} briefing lost the logical sibling path")
    return {"mode": case.name, "skills": len(actual), "payload": "ready", "native_files": "current", "native_activation": "unverified", "log": str(case / "install.log")}


def main() -> int:
    run_root = Path(tempfile.mkdtemp(prefix="pstack-install-probe-")).absolute()
    report = {"installer": "skills@1.5.25", "run_root": str(run_root), "cases": []}
    source_skills = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
    failed = False
    for copy in (False, True):
        try:
            if not source_skills:
                raise AssertionError("source contains no skills")
            report["cases"].append(probe_case(run_root, copy, source_skills))
        except (OSError, ValueError, AssertionError, RuntimeError, subprocess.TimeoutExpired) as error:
            report["cases"].append({"mode": "copy" if copy else "symlink", "error": str(error)})
            failed = True
    rendered = json.dumps(report, indent=2) + "\n"
    (run_root / "report.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
