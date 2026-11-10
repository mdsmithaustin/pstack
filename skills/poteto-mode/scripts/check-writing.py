#!/usr/bin/env python3
"""Check the writing rules a pattern can settle, so no model has to.

  check-writing.py title "<PR or commit title>"
  check-writing.py body <file> [--no-headings]
  check-writing.py prose <file>

`title` checks the Conventional Commits form. `body` checks a PR body for the poteto default
headings in order, then runs the prose checks. Pass --no-headings when the user or the
repository's PR template sets the format. `prose` checks any reply, document, or commit body.

Text inside code fences and backticks is skipped. A `review` line is a place to look, not a
failure. Exit 0: no failure. Exit 1: at least one failure. Exit 2: usage error.
"""
import argparse
import re
import sys
from pathlib import Path

TITLE = re.compile(r"^(feat|fix|docs|refactor|test|chore|perf|build|ci|style|revert)(\([^()\s]+\))?!?: \S(.*\S)?$")
REQUIRED = ["Why", "What changed", "Scope", "Blast Radius", "Verification"]
OPTIONAL = {"Tradeoffs", "Departures from existing patterns", "Demo"}
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"`[^`]*`")
URL = re.compile(r"\bhttps?://\S+")
CONNECTOR_COLON = re.compile(r"\w: [a-z]")
LONG_DASH = "—"


def prose_lines(text):
    """Yield (line number, line with code and URLs blanked) outside code fences."""
    fenced = False
    for number, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, URL.sub("", INLINE.sub("", line))


def check_title(title):
    problems = []
    if not TITLE.match(title):
        problems.append("FAIL title: use `type(scope): subject`, with a type such as feat, fix, docs, refactor, test, chore, or perf.")
    if title.rstrip().endswith("."):
        problems.append("FAIL title: no trailing period.")
    if LONG_DASH in title:
        problems.append("FAIL title: contains a long dash.")
    return problems


def check_prose(text):
    problems = []
    for number, line in prose_lines(text):
        if LONG_DASH in line:
            problems.append(f"FAIL line {number}: long dash. Split the sentence or use a comma.")
        stripped = line.strip()
        if stripped.startswith(("|", "#")) or stripped.endswith(":"):
            continue
        if CONNECTOR_COLON.search(re.sub(r"^\s*([-*]|\d+\.)\s+", "", line)):
            problems.append(f"review line {number}: a colon may join two clauses mid-sentence. A colon before a list is fine.")
    return problems


def check_body(text, headings):
    problems = []
    if headings:
        found = [match.group(1).strip() for match in re.finditer(r"^## (.+)$", text, re.M)]
        known = [name for name in found if name in REQUIRED]
        for name in REQUIRED:
            if name not in found:
                problems.append(f"FAIL body: missing `## {name}`. State a known gap instead of leaving the section out.")
        if known != [name for name in REQUIRED if name in known]:
            problems.append("FAIL body: headings are out of order. Use " + ", ".join(REQUIRED) + ".")
        for name in found:
            if name not in REQUIRED and name not in OPTIONAL:
                problems.append(f"review body: `## {name}` is not a poteto default heading.")
    return problems + check_prose(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    kinds = parser.add_subparsers(dest="kind", required=True)
    kinds.add_parser("title").add_argument("text")
    body = kinds.add_parser("body")
    body.add_argument("file", type=Path)
    body.add_argument("--no-headings", action="store_true")
    kinds.add_parser("prose").add_argument("file", type=Path)
    args = parser.parse_args(argv)
    if args.kind == "title":
        problems = check_title(args.text)
    else:
        try:
            text = args.file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"check-writing.py: {error}", file=sys.stderr)
            return 2
        problems = check_body(text, not args.no_headings) if args.kind == "body" else check_prose(text)
    for problem in problems:
        print(problem)
    failed = any(problem.startswith("FAIL") for problem in problems)
    if not problems:
        print("PASS")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
