#!/usr/bin/env python3
"""Fail on unconditional mentions of another suite's skills.

A skill suite must run on its own. Naming a skill from a different suite is
fine only as an optional capability: the sentence must say what happens when
that skill is absent. This check scans skills/**/*.md for foreign skill names
written as skill references (**name**, `name`, /name, $name, "name skill")
and requires a conditional marker in the same paragraph.

Three things are not dependencies and pass:
- an indefinite category ("a code-review skill", "the relevant triage skill");
- a mention scoped to a foreign-managed target ("for GSD-related targets");
- a mention inside an adapter file (*-bridge.md, *-adapters.md), which is the
  one place cross-suite coupling is allowed to live.
Names that are also this suite's own vocabulary (a loop type called
`research`) are excluded with --ignore.

Usage: check-cross-suite-references.py --foreign a,b,c [--foreign-prefix gsd-]
       [--ignore research] [--adapter-glob '*-bridge.md,*-adapters.md'] [skills_root]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CONDITIONAL = re.compile(
    r"\b(if|when|where|whenever)\b[^.\n]{0,80}\b(installed|available|present|exists|supplied|discovered|offers|provides)\b"
    r"|\b(otherwise|fallback|fall back|absent|unavailable|not installed|for example|such as|e\.g\.|any similarly-named|or equivalent|equivalent workflow)\b"
    r"|\b(a|an|any|the relevant|a relevant|a plain|a similarly-named)\s+[\w-]+\s+skill\b"
    r"|\b[\w-]+-(related|managed|owned)\b|\bfor [\w-]+ targets\b",
    re.IGNORECASE,
)


def reference_pattern(names: list[str], prefixes: list[str]) -> re.Pattern[str]:
    alts = [re.escape(n) for n in names] + [re.escape(p) + r"[a-z0-9-]+" for p in prefixes]
    name = "(?:" + "|".join(alts) + ")"
    return re.compile(
        r"\*\*(" + name + r")\*\*"
        r"|`(" + name + r")`"
        r"|(?<![\w/])/(" + name + r")\b"
        r"|\$(" + name + r")\b"
        r"|\b(" + name + r") skill\b"
    )


def paragraphs(text: str):
    """Yield (start_line, paragraph_text), skipping fenced code."""
    lines = text.splitlines()
    buf: list[str] = []
    start = 1
    fence = None
    for i, line in enumerate(lines, start=1):
        s = line.lstrip()
        if s.startswith(("```", "~~~")):
            marker = s[:3]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        if not line.strip():
            if buf:
                yield start, "\n".join(buf)
                buf = []
            continue
        if not buf:
            start = i
        buf.append(line)
    if buf:
        yield start, "\n".join(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--foreign", default="", help="comma-separated foreign skill names")
    ap.add_argument("--foreign-file", type=Path, help="roster file: one skill name per line; 'prefix:gsd-' lines add a prefix; 'ignore:research' lines add an ignore; '#' comments")
    ap.add_argument("--foreign-prefix", default="", help="comma-separated name prefixes, e.g. gsd-")
    ap.add_argument("--ignore", default="", help="comma-separated foreign names that are also this suite's own vocabulary")
    ap.add_argument("--adapter-glob", default="*-bridge.md,*-adapters.md", help="comma-separated globs of adapter files exempt from the rule")
    ap.add_argument("root", nargs="?", default="skills")
    args = ap.parse_args()
    ignore = {n for n in args.ignore.split(",") if n}
    names = [n for n in args.foreign.split(",") if n]
    prefixes_extra: list[str] = []
    if args.foreign_file:
        for raw in args.foreign_file.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("prefix:"):
                prefixes_extra.append(line.split(":", 1)[1].strip())
            elif line.startswith("ignore:"):
                ignore.add(line.split(":", 1)[1].strip())
            else:
                names.append(line)
    names = [n for n in names if n not in ignore]
    adapter_globs = [g for g in args.adapter_glob.split(",") if g]
    prefixes = [p for p in args.foreign_prefix.split(",") if p] + prefixes_extra
    if not names and not prefixes:
        ap.error("no foreign names: pass --foreign or --foreign-file")
    pat = reference_pattern(names, prefixes)
    root = Path(args.root)
    prefixes = [p for p in args.foreign_prefix.split(",") if p] + prefixes_extra
    if not names and not prefixes:
        ap.error("no foreign names: pass --foreign or --foreign-file")
    pat = reference_pattern(names, prefixes)
    root = Path(args.root)
    violations: list[str] = []
    mentions = 0
    adapter_mentions = 0
    for path in sorted(root.rglob("*.md")):
        is_adapter = any(path.match(g) for g in adapter_globs)
        for start, para in paragraphs(path.read_text(encoding="utf-8")):
            found = {m.group(m.lastindex) for m in pat.finditer(para)}
            if not found:
                continue
            mentions += len(found)
            if is_adapter:
                adapter_mentions += len(found)
                continue
            if CONDITIONAL.search(para):
                continue
            violations.append(f"{path}:{start}: unconditional reference to {sorted(found)}")
    for v in violations:
        print(v)
    print(
        f"cross-suite: {mentions} foreign mentions ({adapter_mentions} in adapter files), "
        f"{len(violations)} unconditional",
        file=sys.stderr,
    )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
