#!/usr/bin/env python3
"""Lint pstack-models.md files: role names, model/effort grammar, harness sections.

Usage: python3 check-models-config.py <file> [<file>...]
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESSES = {"codex", "claude-code", "hermes"}

ROLES = {
    "feature", "refactoring", "bug-fix", "perf-issue", "hillclimb",
    "judgment and prose", "hardest tasks", "how explorer", "how explainer",
    "how critics", "why investigators", "why synthesizer", "reflect tooling",
    "reflect judgment", "reflect divergent", "reflect synthesizer",
    "arena runners", "arena cross-judge pool", "swarm workers",
    "architect runners", "interrogate reviewers",
    "trail reviewer", "default",
}
PANEL_ROLES = {
    "how critics", "arena runners", "arena cross-judge pool",
    "architect runners", "interrogate reviewers",
}
REFLECT_SHORTHANDS = {"divergent", "synthesizer", "tooling", "judgment"}

ALLOWED_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max", "ultra"}
NOTICE_EFFORTS = {"max", "ultra"}
GPT56_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
GPT56_SOL_EFFORTS = GPT56_EFFORTS | {"ultra"}
CLAUDE_ALIASES = {"fable", "opus", "sonnet", "haiku"}
CLAUDE_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
OTHER_ALIASES = {"inherit-parent", "auto"}


def _model_effort_allowed(model: str, effort: str) -> bool | None:
    if model.startswith("gpt-5.6-"):
        return effort in (GPT56_SOL_EFFORTS if model == "gpt-5.6-sol" else GPT56_EFFORTS)
    if model in CLAUDE_ALIASES:
        return effort in CLAUDE_EFFORTS
    return None


def _is_valid_model_name(model: str) -> bool:
    if model in OTHER_ALIASES:
        return True
    return bool(model) and model[0].isalnum() and all(c.isalnum() or c in "._-" for c in model)


def _expand_names(raw_names: list[str]) -> list[str]:
    if not raw_names:
        return raw_names
    reflect_group = raw_names[0].startswith("reflect ")
    expanded = [raw_names[0]]
    for name in raw_names[1:]:
        if reflect_group and name in REFLECT_SHORTHANDS and not name.startswith("reflect "):
            expanded.append(f"reflect {name}")
        else:
            expanded.append(name)
    return expanded


def _parse_entries(entries_str: str, line_no: int, findings: list[tuple[int, str, str]]):
    entries: list[tuple[str, str | None]] = []
    for raw in entries_str.split(","):
        entry = raw.strip()
        if not entry:
            findings.append((line_no, "error", "empty entry"))
            continue
        model, _, effort = entry.partition("@")
        model = model.strip()
        effort = effort.strip() if "@" in entry else None

        if not model:
            findings.append((line_no, "error", f"empty model in entry {entry!r}"))
            continue
        if not _is_valid_model_name(model):
            findings.append((line_no, "error", f"invalid model name {model!r}"))
            continue

        if effort is not None:
            if not effort:
                findings.append((line_no, "error", f"empty effort in entry {entry!r}"))
                continue
            if effort not in ALLOWED_EFFORTS:
                findings.append((line_no, "error", f"unknown effort {effort!r} for model {model!r}"))
                continue
            if _model_effort_allowed(model, effort) is False:
                findings.append((line_no, "error", f"effort {effort!r} not supported by model {model!r}"))
                continue
            if effort in NOTICE_EFFORTS:
                findings.append((line_no, "notice", f"{model}@{effort} pins an expensive tier"))
        entries.append((model, effort))
    return entries


def parse(text: str) -> tuple[dict, list]:
    findings: list[tuple[int, str, str]] = []
    sections: dict[str, dict[str, list[tuple[str, str | None]]]] = {"": {}}
    lines = text.splitlines()

    body_start = 0
    if lines and lines[0].strip() == "---":
        close_idx = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if close_idx is None:
            findings.append((1, "error", "unclosed frontmatter fence"))
            body_start = len(lines)
        else:
            body_start = close_idx + 1

    current_section = ""
    headers_seen: set[str] = set()
    roles_seen: dict[str, set[str]] = {"": set()}

    for i in range(body_start, len(lines)):
        line_no, raw = i + 1, lines[i]
        stripped = raw.strip()
        if not stripped:
            continue

        if stripped.startswith("##"):
            header = stripped[2:].strip()
            if header not in HARNESSES:
                findings.append((line_no, "error", f"unknown section header {stripped!r}"))
            elif header in headers_seen:
                findings.append((line_no, "error", f"duplicate section {header!r}"))
            else:
                headers_seen.add(header)
                current_section = header
                sections.setdefault(header, {})
                roles_seen.setdefault(header, set())
            continue
        if stripped.startswith("#"):
            continue
        if ":" not in raw:
            findings.append((line_no, "error", f"malformed role line {raw!r}"))
            continue

        names_str, entries_str = raw.split(":", 1)
        raw_names = [n.strip() for n in names_str.split(",")]
        if any(not n for n in raw_names):
            findings.append((line_no, "error", "empty role name"))
            raw_names = [n for n in raw_names if n]
        if not raw_names:
            continue

        names = _expand_names(raw_names)
        entries = _parse_entries(entries_str, line_no, findings)
        if not entries:
            continue

        for name in names:
            if name not in ROLES:
                findings.append((line_no, "error", f"unknown role {name!r}"))
            elif name in roles_seen[current_section]:
                findings.append((line_no, "error", f"role {name!r} bound twice in section {current_section!r}"))
            elif name not in PANEL_ROLES and len(entries) > 1:
                roles_seen[current_section].add(name)
                findings.append((line_no, "error", f"single-value role {name!r} given a list"))
            else:
                roles_seen[current_section].add(name)
                sections[current_section][name] = entries

    return sections, findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check-models-config.py <file> [<file>...]", file=sys.stderr)
        return 1
    exit_code = 0
    for path in argv[1:]:
        text = Path(path).read_text(encoding="utf-8")
        _, findings = parse(text)
        for line_no, level, message in findings:
            print(f"{path}:{line_no}: {level}: {message}")
            if level == "error":
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
