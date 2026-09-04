#!/usr/bin/env python3
"""Every skills/*/SKILL.md has frontmatter whose name equals its directory, a non-empty description, no tabs, and no duplicate top-level key."""
from __future__ import annotations

import re
import sys
from pathlib import Path

FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
KV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")


def is_indented(line: str) -> bool:
    return line[:1] in (" ", "\t")


def quote_error(value: str) -> str | None:
    if not value.startswith('"'):
        return None
    if len(value) < 2 or not value.endswith('"'):
        return "quoted value is not terminated"
    inner = value[1:-1]
    i = 0
    while i < len(inner):
        c = inner[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return "quoted value has an unescaped interior quote"
        i += 1
    if i > len(inner):
        return "quoted value is not terminated"
    return None


def block_errors(block_lines: list[str], first_line_no: int) -> list[str]:
    """Only checks that need no YAML grammar. Anything requiring real parsing stays out."""
    errors: list[str] = []
    seen_keys: dict[str, int] = {}
    for offset, raw in enumerate(block_lines):
        lineno = first_line_no + offset
        if "\t" in raw:
            errors.append(f"{lineno}: tab character in frontmatter")
        if not raw.strip():
            continue
        if is_indented(raw):
            continue
        m = KV_LINE.match(raw)
        if not m:
            continue
        key = m.group(1)
        if key in seen_keys:
            errors.append(f"{lineno}: duplicate key {key!r}, first seen at line {seen_keys[key]}")
        else:
            seen_keys[key] = lineno
    return errors


def top_level_fields(block_lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in block_lines:
        if not raw.strip() or is_indented(raw):
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        fields.setdefault(key.strip(), value.strip().strip('"'))
    return fields


def main(root: Path) -> int:
    errors: list[str] = []
    skill_files = sorted(root.glob("*/SKILL.md"))
    for skill_md in skill_files:
        text = skill_md.read_text(encoding="utf-8")
        m = FM.match(text)
        if not m:
            errors.append(f"{skill_md}: missing frontmatter")
            continue
        block_lines = m.group(1).splitlines()
        for be in block_errors(block_lines, first_line_no=2):
            errors.append(f"{skill_md}:{be}")
        fields = top_level_fields(block_lines)
        if fields.get("name") != skill_md.parent.name:
            errors.append(f"{skill_md}: name {fields.get('name')!r} != directory {skill_md.parent.name!r}")
        if not fields.get("description"):
            errors.append(f"{skill_md}: empty description")
    for e in errors:
        print(e)
    print(f"frontmatter: {len(skill_files)} skills, {len(errors)} errors", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "skills")))
