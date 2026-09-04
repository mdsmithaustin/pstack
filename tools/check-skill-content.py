#!/usr/bin/env python3
"""Fail on broken content inside skills/**/*.md.

Every relative markdown link whose target ends in .md must resolve to a file. Every bolded name that
reads as a skill reference must name a real directory under the skills root. A
principle- prefix always reads as one. Any other kebab name reads as one only
when "skill" appears on the same line. On a line mentioning a principle, a bare
name also resolves against its principle- directory, which is how the suite
writes "the **model-the-domain** principle skill".
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import unquote

ROOT = Path("skills")
IGNORE: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    lines: list[str]


LINK_TARGET = re.compile(r"\]\(([^)\s<>]+\.md(?:#[^)\s]*)?)\)")
CODE_TARGET = re.compile(r"`(\.\.?/[^`\s<>]+)`")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(```|~~~)")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def outside_fences(lines: list[str]) -> Iterator[tuple[int, str]]:
    marker: str | None = None
    for lineno, line in enumerate(lines, start=1):
        m = FENCE.match(line)
        if m:
            marker = None if marker == m.group(1) else (marker or m.group(1))
            continue
        if marker is None:
            yield lineno, line


def check_relative_links(parsed: ParsedFile) -> Iterator[Finding]:
    for lineno, line in outside_fences(parsed.lines):
        for pattern in (LINK_TARGET, CODE_TARGET):
            for m in pattern.finditer(line):
                target = unquote(m.group(1).split("#", 1)[0])
                if not target or SCHEME.match(target) or target.startswith("/"):
                    continue
                resolved = parsed.path.parent / target
                ok = resolved.is_file() if target.endswith(".md") else resolved.exists()
                if not ok:
                    yield Finding(
                        parsed.path,
                        lineno,
                        "relative-link",
                        f"target does not exist: {target}",
                    )


BOLD_NAME = re.compile(r"\*\*([a-z][a-z0-9-]*)\*\*")


def check_sibling_skill(parsed: ParsedFile) -> Iterator[Finding]:
    for lineno, raw in outside_fences(parsed.lines):
        line = INLINE_CODE.sub("``", raw)
        near_skill = "skill" in line
        principle_hint = "principle" in line
        for m in BOLD_NAME.finditer(line):
            name = m.group(1)
            if name in IGNORE:
                continue
            # A principle- prefix names a skill unambiguously. Any other bolded
            # kebab word needs "skill" nearby, or ordinary emphasis in prose
            # (glossary terms, enum bullets) would flood the findings.
            if not name.startswith("principle-") and not near_skill:
                continue
            if (ROOT / name).is_dir():
                continue
            if principle_hint and (ROOT / f"principle-{name}").is_dir():
                continue
            yield Finding(
                parsed.path,
                lineno,
                "sibling-skill",
                f"**{name}** has no matching directory under {ROOT}/",
            )


REGISTRY: list[tuple[str, Callable[[ParsedFile], Iterator[Finding]]]] = [
    ("relative-link", check_relative_links),
    ("sibling-skill", check_sibling_skill),
]


def iter_markdown_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.md")):
        if "node_modules" in path.parts:
            continue
        yield path


def main() -> int:
    global ROOT, IGNORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--ignore", default="", help="comma-separated bolded names to never treat as skill references")
    ap.add_argument("root", nargs="?", default="skills")
    args = ap.parse_args()
    ROOT = Path(args.root)
    IGNORE = frozenset(n for n in args.ignore.split(",") if n)

    findings: list[Finding] = []
    files_checked = 0
    for path in iter_markdown_files(ROOT):
        files_checked += 1
        parsed = ParsedFile(path, path.read_text(encoding="utf-8").splitlines())
        for _name, check in REGISTRY:
            findings.extend(check(parsed))

    findings.sort(key=lambda f: (str(f.path), f.line, f.kind))
    for f in findings:
        print(f)
    print(f"content: {files_checked} files, {len(findings)} findings", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
