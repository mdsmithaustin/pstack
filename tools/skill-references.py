#!/usr/bin/env python3
"""Fail on a slash or dollar skill spelling that no exemption covers, a load written "Use the **name** skill", or a skill name that no skill defines, in model-facing text.

The scan covers tracked markdown under skills/ that is still present on disk, so deleted
files, an installed node_modules, or another untracked file never fail it. Root agents/*.md
is out of scope because PORTING.md keeps it as upstream text, including Comment Sicko's
/how and /why and poteto-agent's /poteto-mode.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]

USER_FACING_SKILLS = frozenset({"poteto-help"})
USER_FACING = {
    "skills/architect/SKILL.md": ['"/architect with checkpoint,"'],
    "skills/create-formal-verification-skill/SKILL.md": ["Point the user at `/maintain-formal-verification-skill`"],
    "skills/create-verification-skill/SKILL.md": ["Point the user at `/maintain-verification-skill`"],
    "skills/deslop/SKILL.md": ["and on `/deslop`,"],
    "skills/ketchup/SKILL.md": ["the last message they wrote before `/ketchup`"],
    "skills/ketchup-video/SKILL.md": ["the last message the user wrote before `/ketchup-video`, not before any earlier `/ketchup`"],
    "skills/maintain-formal-verification-skill/SKILL.md": ["point at `/create-formal-verification-skill`"],
    "skills/maintain-verification-skill/SKILL.md": ["point at `/create-verification-skill`"],
    "skills/pstack-harness/references/roles.md": ["Run `/setup-pstack` to register it.\""],
    "skills/reflect/SKILL.md": ['the user says "reflect" or "/reflect"'],
    "skills/setup-pstack/SKILL.md": ["4 of 4 `/poteto-mode` runs",
                                     "I can generate one with /create-verification-skill.\"",
                                     "I can generate one with /create-formal-verification-skill.\""],
}
MODE_REMINDERS = {
    "skills/poteto-mode/SKILL.md": ["apply /poteto-mode."],
}
EXEMPT = {rel: USER_FACING.get(rel, []) + MODE_REMINDERS.get(rel, []) for rel in USER_FACING | MODE_REMINDERS}


class Sigil(NamedTuple):
    file: str
    line: int
    spelling: str
    text: str
    in_description: bool


def skill_names(root: Path) -> list[str]:
    return sorted(p.parent.name for p in (root / "skills").glob("*/SKILL.md"))


def model_facing_files(root: Path) -> list[Path]:
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "skills/*.md"],
                             check=True, capture_output=True, text=True).stdout
    return sorted(root / rel for rel in tracked.split("\0") if rel and (root / rel).is_file())


def sigil_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w./}}-])[/$]{re.escape(name)}(?![\w/-])")


def description_lines(lines: list[str]) -> set[int]:
    """Line numbers of the frontmatter `description:` value, including a folded continuation."""
    if not lines or lines[0].strip() != "---":
        return set()
    found: set[int] = set()
    inside = False
    for number, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            inside = True
        elif inside and not line.startswith((" ", "\t")):
            inside = False
        if inside:
            found.add(number)
    return found


def sigils(root: Path = ROOT) -> list[Sigil]:
    compiled = {name: sigil_pattern(name) for name in skill_names(root)}
    hits = []
    for path in model_facing_files(root):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        described = description_lines(lines)
        for number, line in enumerate(lines, 1):
            for pattern in compiled.values():
                hits += [Sigil(rel, number, match.group(0), line, number in described)
                         for match in pattern.finditer(line)]
    return hits


def exempt(hit: Sigil) -> bool:
    skill = hit.file.split("/")[1]
    if skill in USER_FACING_SKILLS:
        return True
    if hit.file == f"skills/{skill}/SKILL.md" and hit.spelling == f"/{skill}" and hit.in_description:
        return True
    return any(hit.spelling in passage and passage in hit.text for passage in EXEMPT.get(hit.file, ()))


def violations(root: Path = ROOT) -> list[str]:
    return [f"{hit.file}:{hit.line}: {hit.spelling}" for hit in sigils(root) if not exempt(hit)]


def stale_exemptions(root: Path = ROOT) -> list[str]:
    hits = sigils(root)
    return [f"{rel}: {passage}" for rel, passages in EXEMPT.items() for passage in passages
            if not any(hit.file == rel and hit.spelling in passage and passage in hit.text for hit in hits)]


LEGACY_LOAD = re.compile(r"\b[Uu]se the \*\*[a-z0-9][a-z0-9-]*\*\* skill\b")
SKILL_TOOL_NAME = re.compile(r"\bSkill tool with `([a-z0-9][a-z0-9-]*)`")
BOLD_SKILL = re.compile(r"\*\*([a-z0-9][a-z0-9-]*)\*\*(?=(?:\s+[a-z-]+){0,2}\s+skill\b)")
BOLD_NAME = re.compile(r"\*\*([a-z0-9]+(?:-[a-z0-9]+)+)\*\*")


def legacy_loads(root: Path = ROOT) -> list[str]:
    return [f"{path.relative_to(root).as_posix()}:{number}: {match.group(0)}"
            for path in model_facing_files(root)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            for match in LEGACY_LOAD.finditer(line)]


def unresolved_names(root: Path = ROOT) -> list[str]:
    names = set(skill_names(root))
    rows = []
    for path in model_facing_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            named = set(BOLD_SKILL.findall(line))
            named |= {name for name in BOLD_NAME.findall(line) if f"principle-{name}" in names}
            rows += [f"{rel}:{number}: **{name}**" for name in sorted(named - names)]
            rows += [f"{rel}:{number}: `{name}`" for name in sorted(set(SKILL_TOOL_NAME.findall(line)) - names)]
    return rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    found = violations()
    stale = stale_exemptions()
    legacy = legacy_loads()
    unresolved = unresolved_names()
    for row in found + legacy:
        print(f"{row}: write \"Call the Skill tool with `name`.\" as its own sentence or step")
    for row in stale:
        print(f"{row}: stale exemption, remove it")
    for row in unresolved:
        print(f"{row}: no skill has this name; write the full name, such as **principle-prove-it-works**")
    return 1 if found or legacy or stale or unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
