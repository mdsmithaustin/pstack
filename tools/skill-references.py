#!/usr/bin/env python3
"""List every sibling-skill reference in model-facing skill text, one TSV row per reference.

Columns: file, line, skill, form, shape, sentence. `form` is how the text spells the name (sigil, bold, code,
link, plain). `shape` is `use` when the sentence is the load form "Use the **x** skill", else `other`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\[(\"'])")
LIST_MARK = r"(?:\s*(?:[-*]|\d+[.)])\s+)?(?:\*\*[^*]+\*\*\s+)?"


class Ref(NamedTuple):
    file: str
    line: int
    skill: str
    form: str
    shape: str
    sentence: str


def skill_names(root: Path) -> list[str]:
    return sorted(p.parent.name for p in (root / "skills").glob("*/SKILL.md"))


def model_facing_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "skills").rglob("*.md") if p.is_file())


def patterns(name: str) -> dict[str, re.Pattern[str]]:
    n = re.escape(name)
    spelled = rf"(?:{n}|{re.escape(name.removeprefix('principle-'))})" if name.startswith("principle-") else n
    return {
        "sigil": re.compile(rf"(?<![\w./}}-])[/$]{n}(?![\w/-])"),
        "bold": re.compile(rf"(?<!\*)\*\*{spelled}\*\*(?!\*)"),
        "code": re.compile(rf"(?<![\w/$])`{spelled}`"),
        "link": re.compile(rf"\]\((?:\.\./)+{n}/SKILL\.md[^)]*\)"),
        "plain": re.compile(rf"\bthe\s+{spelled}\s+(?:skill|principle skill)\b"),
    }


def use_shape(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?:^{LIST_MARK}|[,→(]\s*|\. )[Uu]se the \*\*{re.escape(name)}\*\* skill\b")


def body_lines(text: str) -> list[tuple[int, str]]:
    """(line number, text) for each line outside the frontmatter and fenced blocks."""
    lines, out, fenced, start = text.splitlines(), [], False, 0
    if lines and lines[0] == "---":
        start = next((i for i in range(1, len(lines)) if lines[i] == "---"), 0) + 1
    for number, line in enumerate(lines[start:], start + 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((number, line))
    return out


def scan(root: Path = ROOT) -> list[Ref]:
    names = skill_names(root)
    compiled = {name: (patterns(name), use_shape(name)) for name in names}
    refs = []
    for path in model_facing_files(root):
        rel = path.relative_to(root).as_posix()
        owner = rel.split("/")[1]
        for number, line in body_lines(path.read_text(encoding="utf-8")):
            for sentence in SENTENCE.split(line):
                for name, (forms, shape) in compiled.items():
                    if name == owner:
                        continue
                    for form, pattern in forms.items():
                        if pattern.search(sentence):
                            refs.append(Ref(rel, number, name, form, "use" if shape.search(sentence) else "other",
                                            sentence.strip()))
    return refs


def sigils(root: Path = ROOT) -> list[tuple[str, int, str, str]]:
    """(file, line, spelling, line text) for every /name or $name of a pstack skill, frontmatter and fences included."""
    compiled = {name: patterns(name)["sigil"] for name in skill_names(root)}
    hits = []
    for path in model_facing_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in compiled.values():
                hits += [(rel, number, match.group(0), line) for match in pattern.finditer(line)]
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--form", action="append", help="only these forms")
    parser.add_argument("--shape", choices=("use", "other"))
    parser.add_argument("--sigils", action="store_true", help="list every /name or $name spelling instead")
    args = parser.parse_args()
    if args.sigils:
        for rel, number, spelling, line in sigils():
            print("\t".join([rel, str(number), spelling, line.strip()]))
        return 0
    for ref in scan():
        if (args.form and ref.form not in args.form) or (args.shape and ref.shape != args.shape):
            continue
        print("\t".join([ref.file, str(ref.line), ref.skill, ref.form, ref.shape, ref.sentence]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
