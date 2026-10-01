#!/usr/bin/env python3
"""Lint pstack-models.md files, or resolve roles to a model and effort for one harness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

HARNESSES = {"codex", "claude-code", "hermes"}

ROLES = {
    "feature", "refactoring", "bug-fix", "perf-issue", "hillclimb",
    "judgment and prose", "hardest tasks", "how explorer", "how explainer",
    "why investigators", "why synthesizer", "reflect tooling",
    "reflect judgment", "reflect divergent", "reflect synthesizer",
    "arena runners", "arena cross-judge pool", "swarm workers",
    "architect runners", "interrogate reviewers",
    "trail reviewer", "default",
}
PANEL_ROLES = {
    "arena runners", "arena cross-judge pool",
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
CLAUDE_CODE_SECTION = "claude-code"
NOT_CLAUDE_CODE_LEVELS = {"none", "ultra"}

INHERIT = "inherit-parent"
CONFIG_NAME = "pstack-models.md"
SKILL_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "examples" / CONFIG_NAME

HARNESS_EFFORTS = {
    "claude-code": CLAUDE_EFFORTS,
    "codex": ALLOWED_EFFORTS,
    "hermes": ALLOWED_EFFORTS,
}
SESSION_EFFORT_HARNESSES = {"claude-code"}
CODEX_ALIAS_TRANSLATION = {
    "fable": ("gpt-5.6-sol", "max"),
    "opus": ("gpt-5.6-sol", "xhigh"),
    "sonnet": ("gpt-5.6-terra", "high"),
    "haiku": ("gpt-5.6-luna", "high"),
}
XHIGH_FLOOR_ROLES = {
    "hardest tasks", "judgment and prose", "bug-fix", "perf-issue", "hillclimb",
    "how explainer", "why synthesizer", "reflect judgment", "reflect divergent",
    "reflect synthesizer", "arena cross-judge pool", "architect runners",
    "trail reviewer",
}
DEFAULT_EFFORT_FLOOR = "high"


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


def _parse_entries(entries_str: str, line_no: int, findings: list[tuple[int, str, str]], section: str) -> tuple[list[tuple[str, str | None]], list[int]]:
    entries: list[tuple[str, str | None]] = []
    deferred_flat_notices: list[int] = []
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
            if section == CLAUDE_CODE_SECTION and effort in NOT_CLAUDE_CODE_LEVELS:
                findings.append((line_no, "error", f"effort {effort!r} is not a Claude Code level (low, medium, high, xhigh, max)"))
                continue
            if effort in NOTICE_EFFORTS:
                findings.append((line_no, "notice", f"{model}@{effort} pins an expensive tier"))
            if section == "" and effort in NOT_CLAUDE_CODE_LEVELS:
                deferred_flat_notices.append(line_no)
        entries.append((model, effort))
    return entries, deferred_flat_notices


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
    pending_flat_notices: list[tuple[int, str]] = []

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
        entries, deferred_flat_notices = _parse_entries(entries_str, line_no, findings, current_section)
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
                if current_section == "":
                    for ln in deferred_flat_notices:
                        pending_flat_notices.append((ln, name))

    claude_code_roles = sections.get(CLAUDE_CODE_SECTION, {})
    for line_no, name in pending_flat_notices:
        if name not in claude_code_roles:
            findings.append((line_no, "notice", f"Claude Code cannot use none or ultra, so it runs `{name}` at the session effort"))

    return sections, findings


class Layer(NamedTuple):
    source: str
    roles: dict[str, list[tuple[str, str | None]]]


class ResolvedArm(NamedTuple):
    role: str
    arm: int
    model: str
    effort: str
    source: str
    notes: tuple[str, ...] = ()

    def to_json(self) -> str:
        record: dict = {
            "role": self.role, "arm": self.arm, "model": self.model,
            "effort": self.effort, "source": self.source,
        }
        if self.notes:
            record["notes"] = list(self.notes)
        return json.dumps(record)


def _resolve_model(model: str, harness: str) -> tuple[str, str | None, list[str]]:
    if model in OTHER_ALIASES:
        return INHERIT, None, []
    usable = model in CLAUDE_ALIASES if harness == "claude-code" else model not in CLAUDE_ALIASES
    if usable:
        return model, None, []
    if harness == "codex" and model in CLAUDE_ALIASES:
        translated_model, translated_effort = CODEX_ALIAS_TRANSLATION[model]
        return translated_model, translated_effort, []
    return INHERIT, None, [f"{model} is not usable on {harness}"]


def _resolve_effort(role: str, harness: str, model: str, written: str | None, notes: list[str]) -> str:
    if written is not None:
        if written in HARNESS_EFFORTS[harness] and _model_effort_allowed(model, written) is not False:
            return written
        notes.append(f"effort {written} is not usable on {harness}")
    if harness in SESSION_EFFORT_HARNESSES or model == INHERIT:
        return INHERIT
    return "xhigh" if role in XHIGH_FLOOR_ROLES else DEFAULT_EFFORT_FLOOR


def _resolve_arm(role: str, arm: int, source: str, harness: str, entry: tuple[str, str | None]) -> ResolvedArm:
    written_model, written_effort = entry
    model, translated_effort, notes = _resolve_model(written_model, harness)
    effort_in = written_effort
    if translated_effort is not None:
        effort_in = written_effort or translated_effort
        shown = model if written_effort else f"{model}@{translated_effort}"
        notes.append(f"{written_model} translated to {shown}")
    effort = _resolve_effort(role, harness, model, effort_in, notes)
    return ResolvedArm(role, arm, model, effort, source, tuple(notes))


def resolve_role(role: str, harness: str, layers: list[Layer]) -> list[ResolvedArm]:
    for source, roles in layers:
        if role in roles:
            return [
                _resolve_arm(role, i, source, harness, entry)
                for i, entry in enumerate(roles[role], start=1)
            ]
    raise LookupError(f"no layer binds role {role!r}")


def build_layers(harness: str, workspace: dict, user: dict, skill_default: dict) -> list[Layer]:
    return [
        Layer(f"workspace ## {harness}", workspace.get(harness, {})),
        Layer(f"user ## {harness}", user.get(harness, {})),
        Layer("workspace flat", workspace.get("", {})),
        Layer("user flat", user.get("", {})),
        Layer("skill default", skill_default.get("", {})),
    ]


def _load_layer_file(path: Path) -> tuple[dict, list[tuple[int, str, str]]]:
    if not path.is_file():
        return {}, []
    return parse(path.read_text(encoding="utf-8"))


def _resolve_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="check-models-config.py", allow_abbrev=False)
    parser.add_argument("--resolve", action="store_true", required=True)
    parser.add_argument("--harness", required=True, choices=sorted(HARNESSES))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--user-file", type=Path, default=Path.home() / ".agents" / CONFIG_NAME)
    parser.add_argument("roles", nargs="*", metavar="ROLE")
    args = parser.parse_args(argv)

    unknown = [r for r in args.roles if r not in ROLES]
    if unknown:
        print(f"unknown role {unknown[0]!r}", file=sys.stderr)
        return 2

    workspace_file = args.project / ".agents" / CONFIG_NAME
    parsed = {}
    failed = False
    for path in (workspace_file, args.user_file):
        sections, findings = _load_layer_file(path)
        parsed[path] = sections
        for line_no, level, message in findings:
            if level == "error":
                print(f"{path}:{line_no}: {level}: {message}", file=sys.stderr)
                failed = True
    if failed:
        return 1

    skill_default, _ = parse(SKILL_DEFAULT_FILE.read_text(encoding="utf-8"))
    layers = build_layers(args.harness, parsed[workspace_file], parsed[args.user_file], skill_default)
    for role in args.roles or sorted(ROLES):
        for arm in resolve_role(role, args.harness, layers):
            print(arm.to_json())
    return 0


USAGE = (
    "usage: check-models-config.py <file> [<file>...]\n"
    "       check-models-config.py --resolve --harness {claude-code,codex,hermes}"
    " [--project DIR] [--user-file FILE] [ROLE ...]"
)


def main(argv: list[str]) -> int:
    if "--resolve" in argv[1:]:
        return _resolve_main(argv[1:])
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
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
