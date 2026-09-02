#!/usr/bin/env python3
"""Every skills/*/SKILL.md has frontmatter whose name equals its directory and a non-empty description."""
from __future__ import annotations

import re
import sys
from pathlib import Path

FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def main(root: Path) -> int:
    errors: list[str] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        m = FM.match(text)
        if not m:
            errors.append(f"{skill_md}: missing frontmatter")
            continue
        fields = dict(
            (k.strip(), v.strip().strip('"'))
            for k, v in (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        )
        if fields.get("name") != skill_md.parent.name:
            errors.append(f"{skill_md}: name {fields.get('name')!r} != directory {skill_md.parent.name!r}")
        if not fields.get("description"):
            errors.append(f"{skill_md}: empty description")
    for e in errors:
        print(e)
    print(f"frontmatter: {len(list(root.glob('*/SKILL.md')))} skills, {len(errors)} errors", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "skills")))
