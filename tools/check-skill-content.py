#!/usr/bin/env python3
"""Fail on broken content inside skills/**/*.md.

A relative markdown link whose target ends in .md must resolve to a file. A
relative path written in inline code must resolve to something on disk, whatever
its extension. Fenced blocks, indented code blocks and inline-code spans are skipped, so an
example showing a broken path is not a finding. A fence that is never closed is
itself a finding, because it would silently hide the rest of the file.

A bolded name that reads as a skill reference must name a real directory under
the skills root. A principle- prefix always reads as one. Any other kebab name
reads as one only when "skill" appears on the same line. On a line mentioning a
principle, a bare name also resolves against its principle- directory, which is
how the suite writes "the **model-the-domain** principle skill".
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
    prose: list[tuple[int, str]]
    unclosed_fence: int | None


LINK_TARGET = re.compile(r'\]\(([^)\s<>]+\.md(?:#[^)\s]*)?)(?:\s+"[^"]*")?\)')
CODE_TARGET = re.compile(r"`(\.\.?/[^`\s<>]+)`")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*(.*)$")
INDENTED_CODE = re.compile(r"^ {4,}\S")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def scan_blocks(lines: list[str]) -> tuple[list[tuple[int, str]], int | None]:
    """One fence walk for every caller, so no two checks can disagree about what is code."""
    prose: list[tuple[int, str]] = []
    fence: str | None = None
    opened = 0
    prev_blank = True
    for lineno, line in enumerate(lines, start=1):
        m = FENCE.match(line)
        if m:
            run, info = m.group(1), m.group(2).strip()
            if fence is None:
                fence, opened = run, lineno
            elif run[0] == fence[0] and len(run) >= len(fence) and not info:
                fence = None
            prev_blank = False
            continue
        blank = not line.strip()
        if fence is None and not (prev_blank and INDENTED_CODE.match(line)):
            prose.append((lineno, line))
        prev_blank = blank
    return prose, (opened if fence else None)


def check_relative_links(parsed: ParsedFile) -> Iterator[Finding]:
    for lineno, line in parsed.prose:
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
    for lineno, raw in parsed.prose:
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


def check_unclosed_fence(parsed: ParsedFile) -> Iterator[Finding]:
    opened = parsed.unclosed_fence
    if opened is not None:
        yield Finding(
            parsed.path,
            opened,
            "unclosed-fence",
            "fence opened here is never closed, so the rest of the file goes unchecked",
        )


REGISTRY: list[tuple[str, Callable[[ParsedFile], Iterator[Finding]]]] = [
    ("relative-link", check_relative_links),
    ("sibling-skill", check_sibling_skill),
    ("unclosed-fence", check_unclosed_fence),
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
        prose, unclosed = scan_blocks(path.read_text(encoding="utf-8").splitlines())
        parsed = ParsedFile(path, prose, unclosed)
        for _name, check in REGISTRY:
            findings.extend(check(parsed))

    findings.sort(key=lambda f: (str(f.path), f.line, f.kind))
    for f in findings:
        print(f)
    print(f"content: {files_checked} files, {len(findings)} findings", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
