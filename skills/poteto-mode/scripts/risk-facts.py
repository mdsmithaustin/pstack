#!/usr/bin/env python3
"""Gather the risk evidence a command can gather for the paths a task will touch.

Prints history, reach, and test evidence for each path. It reports evidence, never a
verdict. The lead reads it, judges the five risk facts, and passes them to plan.py.
Every number names its source, so a text search is never read as a call graph.

Reach uses GitNexus when the repository has a `.gitnexus/` index and `gitnexus` is on
PATH, and a text search otherwise. The index reflects the last analyzed commit, so a
symbol that exists only in the working tree is reported as absent from it.

Exit 2 means a usage error, or the project is not a Git repository.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPAIR = re.compile(r"\b(fix|fixes|fixed|revert|hotfix|regression|bug)\b", re.I)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]+$|[._-](test|spec)\.[a-z]+$", re.I)


def git(project, *args):
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)


def history(project, path, days):
    subjects = git(project, "log", "--format=%s", "--follow", "--", path).stdout.splitlines()
    recent = git(project, "log", "--format=%s", f"--since={days}.days", "--", path).stdout.splitlines()
    return {
        "source": "git log",
        "commits": len(subjects),
        f"commits_last_{days}_days": len(recent),
        "repair_commits": sum(1 for subject in subjects if REPAIR.search(subject)),
        "tracked": git(project, "ls-files", "--error-unmatch", "--", path).returncode == 0,
    }


def grep_files(project, word, exclude):
    """Files that name the word, or None when the search itself failed. Exit 1 is git grep's no-match status."""
    done = git(project, "grep", "-l", "-w", "-F", "-e", word)
    if done.returncode not in (0, 1):
        return None
    return sorted(name for name in done.stdout.splitlines() if name != exclude)


def split_tests(files):
    tests = [name for name in files if TEST_PATH.search(name)]
    return [name for name in files if name not in tests], tests


def text_reach(project, word, exclude, kind):
    found = grep_files(project, word, exclude)
    if found is None:
        return {"source": f"git grep ({kind})", "term": word, "unavailable": True, "other_files": None, "files": [],
                "test_files": None, "tests": []}
    callers, tests = split_tests(found)
    return {"source": f"git grep ({kind})", "term": word, "other_files": len(callers), "files": callers[:15],
            "test_files": len(tests), "tests": tests[:15]}


def gitnexus_reach(project, symbol):
    done = subprocess.run(["gitnexus", "impact", symbol], capture_output=True, text=True, cwd=project)
    if done.returncode != 0:
        return None
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return {"source": "gitnexus impact", "term": symbol, "output_lines": len(lines), "output": lines[:40]}


def collect(args):
    project = args.project
    if git(project, "rev-parse", "--git-dir").returncode != 0:
        raise SystemExit("risk-facts.py: not a Git repository. Record history and reach as unknown.")
    notes = []
    indexed = (project / ".gitnexus").is_dir() and shutil.which("gitnexus") is not None
    if indexed:
        refresh = subprocess.run(["gitnexus", "analyze", "--index-only"], capture_output=True, text=True, cwd=project)
        if refresh.returncode != 0:
            indexed = False
            notes.append("gitnexus analyze --index-only failed, so reach falls back to git grep.")
    else:
        notes.append("No GitNexus index or CLI, so reach comes from git grep. A text match is not a call graph.")
    if git(project, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        notes.append("This clone is shallow, so commit counts are a lower bound. Treat a low count as unknown.")
    paths = []
    for path in args.paths:
        entry = {"path": path, "history": history(project, path, args.days)}
        if not entry["history"]["tracked"]:
            entry["note"] = "New or untracked path: no history, and absent from any GitNexus index."
        entry["reach"] = text_reach(project, Path(path).stem, path, "module name")
        paths.append(entry)
    symbols = []
    for symbol in args.symbol:
        reach = gitnexus_reach(project, symbol) if indexed else None
        if indexed and reach is None:
            notes.append(f"gitnexus impact {symbol} failed, so its reach comes from git grep.")
        symbols.append(reach or text_reach(project, symbol, None, "symbol"))
    if not args.symbol:
        notes.append("Pass --symbol for each function, type, or constant you will change to get caller evidence for it.")
    return {"paths": paths, "symbols": symbols, "notes": notes}


def render(report):
    out = []
    for entry in report["paths"]:
        past, reach = entry["history"], entry["reach"]
        recent = next(value for key, value in past.items() if key.startswith("commits_last_"))
        out.append(f"{entry['path']}")
        out.append(f"  history ({past['source']}): {past['commits']} commits, {recent} recent, {past['repair_commits']} that read as repairs")
        if reach.get("unavailable"):
            out.append(f"  reach ({reach['source']}, term `{reach['term']}`): unavailable, the search failed. Record reach as unknown.")
        else:
            out.append(f"  reach ({reach['source']}, term `{reach['term']}`): {reach['other_files']} other files, {reach['test_files']} test files")
        if "note" in entry:
            out.append(f"  note: {entry['note']}")
    for reach in report["symbols"]:
        if reach["source"] == "gitnexus impact":
            out.append(f"{reach['term']} ({reach['source']}): {reach['output_lines']} lines")
            out.extend(f"  {line}" for line in reach["output"])
        elif reach.get("unavailable"):
            out.append(f"{reach['term']} ({reach['source']}): unavailable, the search failed. Record reach as unknown.")
        else:
            out.append(f"{reach['term']} ({reach['source']}): {reach['other_files']} files, {reach['test_files']} test files")
            out.extend(f"  {name}" for name in reach["files"] + reach["tests"])
    out.extend(f"note: {note}" for note in report["notes"])
    out.append("This is evidence for the reach and accumulated complexity facts. Judge consequence, uncertainty, and reversibility yourself. A lookup that failed means unknown, not low.")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="Files the task will touch")
    parser.add_argument("--symbol", action="append", default=[], help="A function, type, or constant the task changes. Repeat for each")
    parser.add_argument("--days", type=int, default=90, help="Window for recent commits")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = collect(args)
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
            return 2
        raise
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
