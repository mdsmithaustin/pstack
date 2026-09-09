#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("skills/pstack-harness/references/subagents/roles.json")
ROLE_SKILLS = {
    "comment-sicko": ["how", "why"],
    "poteto-agent": ["poteto-mode"],
}


def generate(root: Path) -> str:
    paths = sorted((root / "agents").glob("*.md"))
    if {path.stem for path in paths} != set(ROLE_SKILLS):
        raise ValueError("agents/*.md differs from the supported role mapping")
    roles = []
    for path in paths:
        source = path.read_bytes()
        parts = source.decode("utf-8").split("---\n", 2)
        if len(parts) != 3 or parts[0] or not parts[2].strip():
            raise ValueError(f"{path.name}: expected frontmatter and a nonempty body")
        metadata = {}
        for line in parts[1].splitlines():
            key, separator, value = line.partition(": ")
            if not separator or key not in {"name", "description", "is_background"}:
                raise ValueError(f"{path.name}: unsupported frontmatter line {line!r}")
            if key in metadata:
                raise ValueError(f"{path.name}: duplicate field {key}")
            if not value or value[0] in "\"'[{>|&*!" or " #" in value:
                raise ValueError(f"{path.name}: unsupported scalar for {key}")
            metadata[key] = value
        if not metadata.get("name") or not metadata.get("description"):
            raise ValueError(f"{path.name}: name and description are required")
        if metadata.get("is_background", "false") not in {"true", "false"}:
            raise ValueError(f"{path.name}: is_background must be true or false")
        roles.append({
            "id": path.stem,
            "aliases": list(dict.fromkeys([path.stem, metadata["name"]])),
            "description": metadata["description"],
            "body": parts[2],
            "background": metadata.get("is_background") == "true",
            "skills": ROLE_SKILLS[path.stem],
            "source_sha256": hashlib.sha256(source).hexdigest(),
        })
    return json.dumps({"schema_version": 1, "roles": roles}, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate installed personas from upstream agents.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        expected = generate(ROOT)
        output = ROOT / OUTPUT
        if args.check:
            if not output.is_file() or output.read_bytes() != expected.encode("utf-8"):
                raise ValueError(f"{OUTPUT} is stale; run python3 tools/generate-subagents.py")
            print("Subagent bundle matches both upstream agents.")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(expected, encoding="utf-8")
            print(f"Generated {OUTPUT}")
    except (OSError, ValueError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
