#!/usr/bin/env python3
"""Measure what removing a skill would touch, and keep that number from growing.

For each skill, count the shipped instruction files outside its own directory that name it.
Shipped files are those under skills/ and agents/. A lower count means a cheaper removal.
The baseline in tools/removal-baseline.json is a ratchet: the check fails when a count rises
above it or a skill has no baseline entry, and --update lowers entries but never raises one
unless --allow-raise is passed for a reviewed exception.

  check-removal.py                 check every skill against the baseline
  check-removal.py --report NAME   list the files that name one skill
  check-removal.py --update        rewrite the baseline to the current counts

Exit 0: no count is above its baseline. Exit 1: a count rose, or a skill is unlisted.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(__file__).with_name("removal-baseline.json")
SHIPPED = ("skills", "agents")
TEXT = {".md", ".json", ".py", ".ts", ".mjs", ".sh", ".yaml", ".yml", ".toml", ".txt"}


def mentions(name, text):
    """A skill is named by a code or bold span, a slash command, or a path through its directory."""
    escaped = re.escape(name)
    return re.search(rf"`{escaped}`|\*\*{escaped}\*\*|(?<![\w/-])/{escaped}(?![\w-])|(?<![\w-]){escaped}/|\"{escaped}\"", text) is not None


def dependents(root, name):
    own = root / "skills" / name
    found = []
    for top in SHIPPED:
        for path in sorted((root / top).rglob("*")):
            if not path.is_file() or path.suffix not in TEXT or own in path.parents or "node_modules" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            if mentions(name, text):
                found.append(path.relative_to(root).as_posix())
    return found


def skills(root):
    return sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--report", metavar="NAME")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--allow-raise", action="store_true")
    args = parser.parse_args(argv)
    if args.report:
        files = dependents(args.root, args.report)
        print(f"{len(files)} shipped files outside skills/{args.report} name it:")
        for name in files:
            print(f"  {name}")
        return 0
    counts = {name: len(dependents(args.root, name)) for name in skills(args.root)}
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.is_file() else {}
    if args.update:
        raised = sorted(name for name, count in counts.items() if name in baseline and count > baseline[name])
        if raised and not args.allow_raise:
            print(f"FAIL removal cost: --update would raise {', '.join(raised)}. Remove the new mentions, or pass --allow-raise after review.")
            return 1
        args.baseline.write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {args.baseline.name} for {len(counts)} skills.")
        return 0
    failed = False
    for name, count in counts.items():
        if name not in baseline:
            print(f"FAIL removal cost: {name} has no baseline entry. Run --update.")
            failed = True
        elif count > baseline[name]:
            print(f"FAIL removal cost: {name} is named in {count} shipped files, above its baseline of {baseline[name]}. Run --report {name}.")
            failed = True
    for name in sorted(set(baseline) - set(counts)):
        print(f"note: {name} is in the baseline but no longer a skill. Run --update.")
    if not failed:
        loose = sum(1 for name, count in counts.items() if count < baseline[name])
        print(f"PASS removal cost: {len(counts)} skills at or below baseline" + (f", {loose} below it. Run --update to tighten." if loose else "."))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
