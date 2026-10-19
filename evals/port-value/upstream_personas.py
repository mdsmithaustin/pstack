#!/usr/bin/env python3
"""Register the pinned upstream personas in native Codex format."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

DELIVERY_PREFIX = (
    "Read named pstack skills from ../.agents/skills/<name>/SKILL.md relative to "
    "the application directory. Read each required file in full and resolve its "
    "relative references from its directory. Named sibling skills share this root.\n\n"
)


def render(agents: Path):
    files = {}
    for name in ("poteto-agent", "comment-sicko"):
        source = (agents / f"{name}.md").read_text(encoding="utf-8")
        match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", source, re.S)
        if match is None or f"name: {name}" not in match[1].splitlines():
            raise ValueError(f"invalid upstream persona: {name}")
        description = next(line.removeprefix("description: ") for line in match[1].splitlines()
                           if line.startswith("description: "))
        values = {"name": name, "description": description,
                  "developer_instructions": DELIVERY_PREFIX + match[2]}
        files[f"{name}.toml"] = "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
                                         for key, value in values.items()).encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install",))
    parser.add_argument("--harness", required=True, choices=("codex",))
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    agents = Path(__file__).resolve().parents[1] / "upstream-agents"
    destination = args.project / ".codex/agents"
    files = render(agents)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = destination / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"conflicting native persona: {path}")
        path.write_bytes(content)
    print(json.dumps({"registered": sorted(files), "native_activation": "unverified"}))


if __name__ == "__main__":
    main()
