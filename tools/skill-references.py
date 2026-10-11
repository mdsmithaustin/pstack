#!/usr/bin/env python3
"""List slash and dollar skill spellings in model-facing text, one TSV row per spelling.

The scan covers the markdown under skills/ that git tracks, so an installed node_modules
or another untracked file never fails it. Root agents/*.md is out of scope because PORTING.md
keeps it as upstream text, including Comment Sicko's /how and /why and poteto-agent's /poteto-mode.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]


class Sigil(NamedTuple):
    file: str
    line: int
    spelling: str
    text: str


def skill_names(root: Path) -> list[str]:
    return sorted(p.parent.name for p in (root / "skills").glob("*/SKILL.md"))


def model_facing_files(root: Path) -> list[Path]:
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "skills/*.md"],
                             check=True, capture_output=True, text=True).stdout
    return sorted(root / rel for rel in tracked.split("\0") if rel and (root / rel).is_file())


def sigil_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w./}}-])[/$]{re.escape(name)}(?![\w/-])")


def sigils(root: Path = ROOT) -> list[Sigil]:
    compiled = {name: sigil_pattern(name) for name in skill_names(root)}
    hits = []
    for path in model_facing_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in compiled.values():
                hits += [Sigil(rel, number, match.group(0), line) for match in pattern.finditer(line)]
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sigils", action="store_true", help="list every /name or $name spelling")
    parser.parse_args()
    for rel, number, spelling, line in sigils():
        print("\t".join([rel, str(number), spelling, line.strip()]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
