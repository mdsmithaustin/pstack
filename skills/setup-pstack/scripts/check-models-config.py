#!/usr/bin/env python3
"""Lint pstack-models.md files, or resolve roles to a model and effort for one harness."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

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

EFFORT_ORDER = ("none", "low", "medium", "high", "xhigh", "max", "ultra")
ALLOWED_EFFORTS = frozenset(EFFORT_ORDER)
NOTICE_EFFORTS = {"max", "ultra"}
CLAUDE_ALIASES = {"fable", "opus", "sonnet", "haiku"}
CLAUDE_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
OTHER_ALIASES = {"inherit-parent", "auto"}
CLAUDE_CODE_SECTION = "claude-code"

INHERIT = "inherit-parent"
CONFIG_NAME = "pstack-models.md"
SKILL_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "examples" / CONFIG_NAME


class Cli(NamedTuple):
    name: str
    efforts: frozenset[str]
    session_effort: bool
    native_aliases: bool
    translation: Mapping[str, tuple[str, str | None]]
    catalog: Path | None


CLIS: dict[str, Cli] = {
    "claude-code": Cli(
        name="Claude Code", efforts=CLAUDE_EFFORTS, session_effort=True, native_aliases=True, translation={},
        catalog=None,
    ),
    "codex": Cli(
        name="Codex", efforts=ALLOWED_EFFORTS, session_effort=False, native_aliases=False,
        translation={
            "fable": ("gpt-6-sol", "max"),
            "opus": ("gpt-6-sol", "xhigh"),
            "sonnet": ("gpt-6-sol", "high"),
            "haiku": ("gpt-6-luna", "high"),
        },
        catalog=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "models_cache.json",
    ),
    "hermes": Cli(
        name="Hermes", efforts=ALLOWED_EFFORTS, session_effort=False, native_aliases=False, translation={},
        catalog=None,
    ),
    "grok": Cli(
        name="Grok Build", efforts=frozenset({"low", "medium", "high", "xhigh"}), session_effort=True, native_aliases=False,
        translation={alias: ("grok-4.7", None) for alias in CLAUDE_ALIASES},
        catalog=None,
    ),
}

MODEL_EFFORTS: dict[str, frozenset[str]] = {
    "gpt-6.1-sol": ALLOWED_EFFORTS - {"none"},
    "gpt-6-astra": ALLOWED_EFFORTS - {"none"},
    "gpt-6-sol": ALLOWED_EFFORTS - {"none"},
    "gpt-6-luna": ALLOWED_EFFORTS - {"none", "ultra"},
    "grok-4.7": frozenset({"low", "medium", "high", "xhigh"}),
    "grok-4.7-build-fast": frozenset({"low", "medium", "high", "xhigh"}),
    **{alias: CLAUDE_EFFORTS for alias in CLAUDE_ALIASES},
}

XHIGH_FLOOR_ROLES = {
    "hardest tasks", "judgment and prose", "bug-fix", "perf-issue", "hillclimb",
    "how explainer", "why synthesizer", "reflect judgment", "reflect divergent",
    "reflect synthesizer", "arena cross-judge pool", "architect runners",
    "trail reviewer",
}
DEFAULT_EFFORT_FLOOR = "high"
GPT6_RELEASES_NEWEST_FIRST = ("gpt-6.1-", "gpt-6-")
TIER_FAMILIES = (
    ("fable", "opus", "sonnet", "haiku"),
    ("astra", "sol", "luna"),
    ("grok-4.7", "grok-4.7-build-fast"),
)
STEP_CEILING = "xhigh"
STEP_UP_FLOOR = "high"


NO_CATALOG: Mapping[str, frozenset[str]] = MappingProxyType({})


def listed_models(catalog: Path) -> Mapping[str, frozenset[str]]:
    try:
        entries = json.loads(catalog.read_text(encoding="utf-8"))["models"]
        return {
            entry["slug"]: frozenset(level["effort"] for level in entry.get("supported_reasoning_levels") or ())
            for entry in entries
            if entry.get("visibility", "list") == "list"
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _model_efforts(model: str, listed: Mapping[str, frozenset[str]]) -> frozenset[str]:
    return listed.get(model) or MODEL_EFFORTS.get(model, ALLOWED_EFFORTS)


def _tier(model: str) -> str:
    prefix = next((p for p in GPT6_RELEASES_NEWEST_FIRST if model.startswith(p)), "")
    return model[len(prefix):]


def _listed_release(model: str, effort: str, listed: Mapping[str, frozenset[str]]) -> str:
    tier = _tier(model)
    if tier == model:
        return model
    for release in GPT6_RELEASES_NEWEST_FIRST:
        candidate = release + tier
        if candidate in listed and effort in _model_efforts(candidate, listed):
            return candidate
    return model


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
            if effort not in MODEL_EFFORTS.get(model, ALLOWED_EFFORTS):
                findings.append((line_no, "error", f"effort {effort!r} not supported by model {model!r}"))
                continue
            if section in CLIS and effort not in CLIS[section].efforts:
                levels = ", ".join(e for e in EFFORT_ORDER if e in CLIS[section].efforts)
                findings.append((line_no, "error", f"effort {effort!r} is not a {CLIS[section].name} level ({levels})"))
                continue
            if effort in NOTICE_EFFORTS:
                findings.append((line_no, "notice", f"{model}@{effort} pins an expensive tier"))
            if section == "" and effort not in CLIS[CLAUDE_CODE_SECTION].efforts:
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
            if header not in CLIS:
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
    step: str | None = None

    def to_json(self) -> str:
        record: dict = {
            "role": self.role, "arm": self.arm, "model": self.model,
            "effort": self.effort, "source": self.source,
        }
        if self.notes:
            record["notes"] = list(self.notes)
        if self.step:
            record["step"] = self.step
        return json.dumps(record)


def _resolve_model(model: str, written_effort: str | None, harness: str) -> tuple[str, str | None, list[str]]:
    if model in OTHER_ALIASES:
        return INHERIT, written_effort, []
    cli = CLIS[harness]
    if (model in CLAUDE_ALIASES) == cli.native_aliases:
        return model, written_effort, []
    if model in cli.translation:
        translated_model, translated_effort = cli.translation[model]
        shown = translated_model if written_effort or translated_effort is None else f"{translated_model}@{translated_effort}"
        return translated_model, written_effort or translated_effort, [f"{model} translated to {shown}"]
    return INHERIT, written_effort, [f"{model} is not usable on {harness}"]


def _nearest_at_or_below(target: str, ranked: list[str]) -> str:
    at_or_below = [e for e in ranked if EFFORT_ORDER.index(e) <= EFFORT_ORDER.index(target)]
    return at_or_below[-1] if at_or_below else ranked[0]


def _resolve_effort(
    role: str, harness: str, model: str, written: str | None, notes: list[str], listed: Mapping[str, frozenset[str]],
) -> str:
    cli = CLIS[harness]
    if written is not None:
        if written not in cli.efforts:
            notes.append(f"effort {written} is not usable on {harness}")
        elif written not in _model_efforts(model, listed):
            notes.append(f"effort {written} is not usable with {model}")
        else:
            return written
    if cli.session_effort or model == INHERIT:
        return INHERIT
    floor = "xhigh" if role in XHIGH_FLOOR_ROLES else DEFAULT_EFFORT_FLOOR
    ranked = [e for e in EFFORT_ORDER if e in _model_efforts(model, listed)]
    if floor in ranked or not ranked:
        return floor
    note = f"effort {floor} is not usable with {model}"
    if note not in notes:
        notes.append(note)
    return _nearest_at_or_below(floor, ranked)


def _resolve_arm(
    role: str, arm: int, source: str, harness: str, entry: tuple[str, str | None], listed: Mapping[str, frozenset[str]],
) -> ResolvedArm:
    entry_model, entry_effort = entry
    base, effort_in, notes = _resolve_model(entry_model, entry_effort, harness)
    model = base
    if model != INHERIT and effort_in is not None:
        model = _listed_release(model, effort_in, listed)
    effort = _resolve_effort(role, harness, model, effort_in, notes, listed)
    if model != INHERIT:
        model = _listed_release(model, effort, listed)
        if model != base:
            notes.append(f"{base} runs as {model}, the newest release this Codex lists with effort {effort}")
    return ResolvedArm(role, arm, model, effort, source, tuple(notes))


def resolve_role(
    role: str, harness: str, layers: list[Layer], listed: Mapping[str, frozenset[str]] = NO_CATALOG,
) -> list[ResolvedArm]:
    for source, roles in layers:
        if role in roles:
            return [
                _resolve_arm(role, i, source, harness, entry, listed)
                for i, entry in enumerate(roles[role], start=1)
            ]
    raise LookupError(f"no layer binds role {role!r}")


def _newest_allowed(tier: str, allowed: frozenset[str]) -> str:
    return next(m for m in (*(r + tier for r in GPT6_RELEASES_NEWEST_FIRST), tier) if m in allowed)


def _shift_effort(base: str, delta: int, floor: str) -> str:
    low, high = EFFORT_ORDER.index(floor), EFFORT_ORDER.index(STEP_CEILING)
    return EFFORT_ORDER[min(max(EFFORT_ORDER.index(base) + delta, low), high)]


def step_reviewer(
    reviewer: ResolvedArm, work_model: str, work_effort: str | None,
    harness: str, allowed: frozenset[str], listed: Mapping[str, frozenset[str]],
) -> ResolvedArm:
    tier = _tier(work_model)
    if reviewer.model == INHERIT or _tier(reviewer.model) != tier:
        return reviewer
    family = next((f for f in TIER_FAMILIES if tier in f), (tier,))
    held = {_tier(m) for m in allowed}
    above = [t for t in family[:family.index(tier)] if t in held]
    below = [t for t in family[family.index(tier) + 1:] if t in held]
    if above:
        step, delta, floor, target_tier = "up", -1, STEP_UP_FLOOR, above[-1]
    elif below:
        step, delta, floor, target_tier = "down", 1, EFFORT_ORDER[0], below[0]
    else:
        step, delta, floor, target_tier = "same-model", 1, EFFORT_ORDER[0], tier
    base = work_effort if work_effort not in (None, INHERIT) else reviewer.effort
    model = reviewer.model if step == "same-model" else _newest_allowed(target_tier, allowed)
    effort = INHERIT
    if base != INHERIT:
        target = _shift_effort(base, delta, floor)
        model = _listed_release(model, target, listed)
        offered = [e for e in EFFORT_ORDER if e in _model_efforts(model, listed) and e in CLIS[harness].efforts]
        effort = _nearest_at_or_below(target, offered) if offered else target
    result = (
        "the config allows no other model in its family, so this is a same-model review"
        if step == "same-model" else f"stepped {step} to {model}"
    )
    note = f"trail reviewer matched work model {work_model}; {result}"
    notes = (*reviewer.notes, note) if step == "same-model" else (note,)
    return reviewer._replace(model=model, effort=effort, notes=notes, step=step)


def build_layers(harness: str, workspace: dict, user: dict, skill_default: dict) -> list[Layer]:
    return [
        Layer(f"workspace ## {harness}", workspace.get(harness, {})),
        Layer(f"user ## {harness}", user.get(harness, {})),
        Layer("workspace flat", workspace.get("", {})),
        Layer("user flat", user.get("", {})),
        Layer(f"skill default ## {harness}", skill_default.get(harness, {})),
        Layer("skill default", skill_default.get("", {})),
    ]


def _load_layer_file(path: Path) -> tuple[dict, list[tuple[int, str, str]]]:
    if not path.is_file():
        return {}, []
    return parse(path.read_text(encoding="utf-8"))


def _work_model(value: str) -> tuple[str, str | None]:
    model, at, effort = value.partition("@")
    if at and effort not in (*EFFORT_ORDER, INHERIT):
        raise argparse.ArgumentTypeError(f"unknown effort {effort!r}")
    return model, effort if at else None


def _claude_alias_of(model: str, harness: str) -> str:
    cli = CLIS[harness]
    full_id = re.fullmatch(r"claude-([a-z]+)(?:-.*)?", model)
    alias = full_id[1] if full_id else model
    if alias in CLAUDE_ALIASES and (cli.native_aliases or alias in cli.translation):
        return alias
    return model


def _resolve_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="check-models-config.py", allow_abbrev=False)
    parser.add_argument("--resolve", action="store_true", required=True)
    parser.add_argument("--harness", required=True, choices=sorted(CLIS))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--user-file", type=Path, default=Path.home() / ".agents" / CONFIG_NAME)
    parser.add_argument("--work-model", type=_work_model, metavar="MODEL[@EFFORT]")
    parser.add_argument("roles", nargs="*", metavar="ROLE")
    args = parser.parse_args(argv)
    if args.work_model:
        work_name, work_written_effort = args.work_model
        work_name = _claude_alias_of(work_name, args.harness)
        if not _is_valid_model_name(work_name):
            parser.error(f"argument --work-model: invalid model name {work_name!r}")
        if CLIS[args.harness].native_aliases and work_name not in CLAUDE_ALIASES | OTHER_ALIASES:
            parser.error(
                f"argument --work-model: {work_name!r} is not a Claude Code model; "
                "use an alias (fable, opus, sonnet, haiku) or a claude-<alias>-... ID"
            )

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
    catalog = CLIS[args.harness].catalog
    listed = listed_models(catalog) if catalog else NO_CATALOG
    if args.work_model:
        work_model, work_effort, work_notes = _resolve_model(work_name, work_written_effort, args.harness)
        unusable = [f"work model {note}; no step applied" for note in work_notes if work_model == INHERIT]
        allowed = frozenset(
            arm.model for role in ROLES for arm in resolve_role(role, args.harness, layers, listed)
        ) - {INHERIT}
    for role in args.roles or sorted(ROLES):
        for arm in resolve_role(role, args.harness, layers, listed):
            if args.work_model and role == "trail reviewer":
                arm = step_reviewer(arm, work_model, work_effort, args.harness, allowed, listed)
                arm = arm._replace(notes=(*arm.notes, *unusable))
            print(arm.to_json())
    return 0


USAGE = (
    "usage: check-models-config.py <file> [<file>...]\n"
    f"       check-models-config.py --resolve --harness {{{','.join(sorted(CLIS))}}}"
    " [--project DIR] [--user-file FILE] [--work-model MODEL[@EFFORT]] [ROLE ...]"
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
