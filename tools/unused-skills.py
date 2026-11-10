#!/usr/bin/env python3
"""List skills that nothing loads, as cleanup candidates for a maintainer to review.

An unused skill is waste. It is not suite size, because it places nothing in a lead's context.
This is a report, not a gate: it always exits 0, and a listed skill may still be worth keeping.

For each skill it shows:
- loaded by: shipped files outside the skill's own directory that name it (under skills/ and agents/).
  A file that only lists skills, such as the principles reference or the help skill, does not count.
- promises: guide promises in evals/promises/ledger.json that the skill owns
- corpus: whether evals/<skill>/ holds an evaluation corpus
- user entry: whether README.md documents it as a slash command a person invokes

A skill is a candidate when nothing loads it and it owns no promise and has no corpus. A skill is
index only when nothing loads it but a promise or corpus still names it, so no step or trigger
reaches it. A skill that only a person invokes shows `user entry: yes`. Judge those by use.

  unused-skills.py           list the candidates
  unused-skills.py --all     list every skill with its four signals
  unused-skills.py --json    print the full report as JSON
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ("skills", "agents")
TEXT = {".md", ".json", ".py", ".ts", ".mjs", ".sh", ".yaml", ".yml", ".toml", ".txt"}
LISTINGS = {
    "skills/setup-pstack/scripts/skill-listing.py",
    "skills/poteto-mode/references/principles.md",
    "skills/poteto-help/SKILL.md",
    "skills/poteto-help/references/recipes.md",
}


def mentions(name, text):
    """A skill is named by a code or bold span, a slash command, a quoted name, or a path through its directory."""
    escaped = re.escape(name)
    return re.search(rf"`{escaped}`|\*\*{escaped}\*\*|(?<![\w/-])/{escaped}(?![\w-])|(?<![\w-]){escaped}/|\"{escaped}\"", text) is not None


def loaded_by(root, name):
    own = root / "skills" / name
    found = []
    for top in SHIPPED:
        for path in sorted((root / top).rglob("*")):
            relative = path.relative_to(root).as_posix()
            if not path.is_file() or path.suffix not in TEXT or own in path.parents or "node_modules" in path.parts:
                continue
            if relative in LISTINGS or relative.endswith("/agents/openai.yaml"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            if mentions(name, text):
                found.append(relative)
    return found


def promises_by_skill(root):
    ledger = root / "evals/promises/ledger.json"
    counts = {}
    if ledger.is_file():
        for promise in json.loads(ledger.read_text(encoding="utf-8"))["promises"].values():
            for skill in {Path(owner).parts[1] for owner in promise.get("owners", []) if owner.startswith("skills/")}:
                counts[skill] = counts.get(skill, 0) + 1
    return counts


def report(root):
    promises = promises_by_skill(root)
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else ""
    rows = {}
    for name in sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md")):
        loads = loaded_by(root, name)
        row = {
            "loaded_by": len(loads),
            "promises": promises.get(name, 0),
            "corpus": (root / "evals" / name).is_dir(),
            "user_entry": re.search(rf"`/{re.escape(name)}`", readme) is not None,
        }
        row["candidate"] = row["loaded_by"] == 0 and row["promises"] == 0 and not row["corpus"]
        row["index_only"] = row["loaded_by"] == 0 and not row["candidate"]
        rows[name] = row
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = report(args.root)
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    shown = rows if args.all else {name: row for name, row in rows.items() if row["candidate"] or row["index_only"]}
    for name, row in shown.items():
        flag = "candidate" if row["candidate"] else "index only" if row["index_only"] else "in use"
        print(f"{name}: {flag}. loaded by {row['loaded_by']} files, {row['promises']} promises, "
              f"corpus {'yes' if row['corpus'] else 'no'}, user entry {'yes' if row['user_entry'] else 'no'}")
    print(f"{sum(row['candidate'] for row in rows.values())} cleanup candidates and "
          f"{sum(row['index_only'] for row in rows.values())} index-only skills of {len(rows)}. Review them. This report gates nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
