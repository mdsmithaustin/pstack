#!/usr/bin/env python3
"""Run the test files that existed at a commit, unedited, against the working tree.

The agent that changes code also edits the tests that disagree with it. This script keeps the
earlier tests out of its reach: it writes the start commit's test files into place, runs exactly
those files against the current code, and restores whatever the working tree held, so a behavior
the earlier tests pinned cannot change silently. The files run in place because tests find the
project through their own location (`Path(__file__).parent / ".."`, fixture directories).

    preserve.py --since <commit> [--project <root>] [--python <exe>] [--report-only]

Exit 0 when every earlier test passes, 1 when any fails or cannot run, 2 when the commit holds no
test files or the arguments are unusable. --report-only prints the same report and exits 0.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEST_DIRS = {"test", "tests"}
MAX_LISTED = 120


def is_test_file(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if not name.endswith(".py") or name == "conftest.py":
        return False
    return any(p in TEST_DIRS for p in parts[:-1]) or name.startswith("test") or name.endswith(("_test.py", "_tests.py"))


def is_support_file(path: str) -> bool:
    """conftest.py, and non-code files that live beside the tests (fixtures)."""
    parts = path.split("/")
    name = parts[-1]
    if name == "conftest.py":
        return True
    return not name.endswith(".py") and any(p in TEST_DIRS for p in parts[:-1])


def git(project: Path, *args: str, check: bool = True, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=not binary, check=check)


def wants_pytest(python: str, project: Path, test_files: list[str], commit: str) -> bool:
    if subprocess.run([python, "-c", "import pytest"], cwd=project, capture_output=True).returncode != 0:
        return False
    if any((project / name).exists() for name in ("pytest.ini", "conftest.py", "tox.ini")):
        return True
    pyproject = project / "pyproject.toml"
    if pyproject.exists() and "[tool.pytest" in pyproject.read_text(errors="ignore"):
        return True
    return any(b"import pytest" in git(project, "show", f"{commit}:{p}", binary=True).stdout for p in test_files)


def run_tests(python: str, project: Path, files: list[str], runner: str) -> tuple[list[str], list[str], str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if runner == "pytest":
        cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE",
               "-o", "python_files=test*.py *_test.py *_tests.py", *files]
        out = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
        text = out.stdout + out.stderr
        failed = re.findall(r"^FAILED (\S+)", text, re.M)
        errors = re.findall(r"^ERROR (\S+)", text, re.M)
    else:
        cmd = [python, "-m", "unittest", *files]
        out = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
        text = out.stdout + out.stderr
        failed = re.findall(r"^FAIL: (\S+ \([\w.]+\))", text, re.M)
        errors = re.findall(r"^ERROR: (\S+ \([\w.]+\))", text, re.M)
    if out.returncode not in (0, 1) and not failed and not errors:
        last = text.strip().splitlines()[-1] if text.strip() else ""
        errors.append(f"{runner} exited {out.returncode} before running the tests: {last}")
    return failed, errors, summary_line(text)


def summary_line(text: str) -> str:
    for line in reversed(text.strip().split("\n")):
        if re.search(r"\b(passed|failed|error|Ran \d+ test|OK|FAILED)\b", line):
            return line.strip()
    return ""


class InPlace:
    """Write the commit's versions of the given paths into the working tree, then put back what was there."""

    def __init__(self, project: Path, commit: str, paths: list[str]):
        self.project, self.commit, self.paths = project, commit, paths
        self.saved: dict[str, bytes | None] = {}
        self.made_dirs: list[Path] = []

    def __enter__(self):
        for rel in self.paths:
            target = self.project / rel
            self.saved[rel] = target.read_bytes() if target.exists() else None
            for parent in reversed(target.parents):
                if parent != self.project and self.project in parent.parents and not parent.exists():
                    parent.mkdir()
                    self.made_dirs.append(parent)
            target.write_bytes(git(self.project, "show", f"{self.commit}:{rel}", binary=True).stdout)
        return self

    def __exit__(self, *exc):
        for rel, content in self.saved.items():
            target = self.project / rel
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        for d in reversed(self.made_dirs):
            shutil.rmtree(d, ignore_errors=True)
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", required=True, help="commit whose test files run against the working tree")
    parser.add_argument("--project", type=Path, default=None, help="a path inside the repository (default: cwd)")
    parser.add_argument("--python", default=None, help="interpreter that has the project's dependencies (default: the project's .venv, else python on PATH)")
    parser.add_argument("--report-only", action="store_true", help="print the report and exit 0 whatever the result")
    args = parser.parse_args(argv)

    start = (args.project or Path.cwd()).resolve()
    top = git(start, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        print(f"preserve: {start} is not inside a git repository", file=sys.stderr)
        return 2
    project = Path(top.stdout.strip())
    resolved = git(project, "rev-parse", "--verify", "-q", f"{args.since}^{{commit}}", check=False)
    if resolved.returncode != 0:
        print(f"preserve: {args.since} is not a commit in {project}", file=sys.stderr)
        return 2
    commit = resolved.stdout.strip()
    venv = next((p for p in (project / ".venv/bin/python", project / "venv/bin/python") if p.exists()), None)
    python = args.python or (str(venv) if venv else None) or shutil.which("python") or sys.executable

    listed = [p for p in git(project, "ls-tree", "-r", "--name-only", commit).stdout.split("\n") if p]
    test_files = [p for p in listed if is_test_file(p)]
    support = [p for p in listed if is_support_file(p)]
    if not test_files:
        print(f"preserve: nothing to preserve, {commit[:10]} holds no test files")
        return 2
    runner = "pytest" if wants_pytest(python, project, test_files, commit) else "unittest"
    with InPlace(project, commit, test_files + support):
        failed, errors, summary = run_tests(python, project, test_files, runner)

    print(f"preserve: {len(test_files)} test file(s) from {commit[:10]} run in place with {runner} against the working tree")
    if summary:
        print(f"  {summary}")
    for name in failed[:MAX_LISTED]:
        print(f"  FAILED {name}")
    for name in errors[:MAX_LISTED]:
        print(f"  ERROR  {name}")
    hidden = len(failed) + len(errors) - MAX_LISTED
    if hidden > 0:
        print(f"  ... {hidden} more")
    if errors:
        print("  An ERROR is a test that raised instead of asserting, or could not run (import, fixture, or collection).")
        print(f"  Ran with {python}; pass --python <interpreter> if the project's dependencies live elsewhere.")
    if failed or errors:
        print("  Each failure needs either a code fix or the playbook's allowed reason before the commit.")
        return 0 if args.report_only else 1
    print("  All earlier tests still pass unedited.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
