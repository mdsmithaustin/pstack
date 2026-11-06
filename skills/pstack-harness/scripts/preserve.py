#!/usr/bin/env python3
"""Run the test files that existed at a commit, unedited, against the working tree.

The agent that changes code also edits the tests that disagree with it. This script keeps the
earlier tests out of its reach: it exports them from the start commit into a scratch directory and
runs them against the current code, so a behavior the earlier tests pinned cannot change silently.

    preserve.py --since <commit> [--project <root>] [--python <exe>] [--report-only]

Exit 0 when every exported test passes, 1 when any fails or cannot be collected, 2 when the commit
holds no test files or the arguments are unusable. --report-only prints the same report and exits 0.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_DIRS = {"test", "tests"}
MAX_LISTED = 40


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    in_test_dir = any(p in TEST_DIRS for p in parts[:-1])
    if name == "conftest.py" or name in ("pytest.ini", "setup.cfg", "tox.ini") and len(parts) == 1:
        return True
    if name.endswith(".py"):
        return in_test_dir or name.startswith("test_") or name.endswith("_test.py")
    return in_test_dir  # fixtures that live beside the tests travel with them


def git(project: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=check)


def export_tests(project: Path, commit: str, dest: Path) -> list[str]:
    listed = git(project, "ls-tree", "-r", "--name-only", commit).stdout.split("\n")
    paths = [p for p in listed if p and is_test_path(p)]
    if not paths:
        return []
    archive = subprocess.run(
        ["git", "-C", str(project), "archive", "--format=tar", commit, "--", *paths],
        capture_output=True, check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return paths


def has_pytest(python: str, project: Path) -> bool:
    probe = subprocess.run([python, "-c", "import pytest"], cwd=project, capture_output=True)
    return probe.returncode == 0


def run_pytest(python: str, project: Path, baseline: Path, env: dict) -> tuple[list[str], list[str], str]:
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE", "--rootdir", str(baseline), str(baseline)]
    out = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
    text = out.stdout + out.stderr
    failed = [tidy(n, project, baseline) for n in re.findall(r"^FAILED (\S+)", text, re.M)]
    errors = [tidy(n, project, baseline) for n in re.findall(r"^ERROR (\S+)", text, re.M)]
    if out.returncode not in (0, 1) and not failed and not errors:
        errors.append(f"pytest exited {out.returncode} before collecting tests")
    return failed, errors, summary_line(text)


def tidy(node: str, project: Path, baseline: Path) -> str:
    """Show a node id relative to the exported tests, not to the scratch directory."""
    for prefix in (str(baseline), os.path.relpath(baseline, project)):
        if node.startswith(prefix):
            return node[len(prefix):].lstrip("/")
    return node


def run_unittest(python: str, project: Path, baseline: Path, env: dict) -> tuple[list[str], list[str], str]:
    cmd = [python, "-m", "unittest", "discover", "-s", str(baseline), "-t", str(baseline), "-p", "test*.py"]
    out = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
    text = out.stdout + out.stderr
    failed = re.findall(r"^FAIL: (\S+ \([\w.]+\))", text, re.M)
    errors = re.findall(r"^ERROR: (\S+ \([\w.]+\))", text, re.M)
    if out.returncode not in (0, 1) and not failed and not errors:
        errors.append(f"unittest exited {out.returncode} before running tests")
    return failed, errors, summary_line(text)


def summary_line(text: str) -> str:
    for line in reversed(text.strip().split("\n")):
        if re.search(r"\b(passed|failed|error|Ran \d+ test|OK|FAILED)\b", line):
            return line.strip()
    return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", required=True, help="commit whose test files run against the working tree")
    parser.add_argument("--project", type=Path, default=None, help="a path inside the repository (default: cwd)")
    parser.add_argument("--python", default=None, help="interpreter that has the project's dependencies (default: python from PATH, else this one)")
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
    python = args.python or shutil.which("python") or sys.executable

    with tempfile.TemporaryDirectory(prefix="pstack-preserve.") as tmp:
        baseline = Path(tmp)
        paths = export_tests(project, commit, baseline)
        if not paths:
            print(f"preserve: nothing to preserve, {commit[:10]} holds no test files")
            return 2
        env = dict(os.environ)
        env["PYTHONPATH"] = str(project) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        runner = "pytest" if has_pytest(python, project) else "unittest"
        failed, errors, summary = (run_pytest if runner == "pytest" else run_unittest)(python, project, baseline, env)

    test_files = [p for p in paths if p.endswith(".py") and Path(p).name != "conftest.py"]
    print(f"preserve: {len(test_files)} test file(s) from {commit[:10]} run with {runner} against the working tree")
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
        print("  An ERROR is a test that could not run (import, fixture, or collection), not a failing assertion.")
    if failed or errors:
        print("  Each failure needs either a code fix or the playbook's allowed reason before the commit.")
        return 0 if args.report_only else 1
    print("  All earlier tests still pass unedited.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
