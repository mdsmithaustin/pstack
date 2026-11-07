#!/usr/bin/env python3
"""Run the test files that existed at a commit, unedited, against the working tree.

The agent that changes code also edits the tests that disagree with it. This script keeps the
earlier tests out of its reach: it writes the start commit's test files into place, runs exactly
those files against the current code, and restores whatever the working tree held, so a behavior
the earlier tests pinned cannot change silently. The files run in place because tests find the
project through their own location (`Path(__file__).parent / ".."`, fixture directories).

    preserve.py --since <commit> [--project <root>] [--python <exe>] [--reasons <file>] [--report-only]

Exit 0 when every earlier test passes, 1 when any fails or cannot run, 2 when the commit holds no
test files or the arguments are unusable. --report-only prints the same report and exits 0.

--reasons names a file of allowed failures. A block names the failing tests it covers, one per
line, then an indented `input:` line naming what those tests sent and an indented `quote:` line
holding the spec sentence that forbids it, in double quotes:

    tests/test_jobs.py::Jobs::test_missing_destination
    tests/test_jobs.py::Jobs::test_relative_destination
      input: a job whose destination is absent or a bare path
      quote: "Every job declares a destination of the form backup://<name>."

The run exits 0 only when every failing test is named by a block that has both lines. A block
that names no failing test, or a test with no block, is reported. The script cannot judge whether
the sentence covers the input; it makes the reason exist, per failure, before the commit.
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


def pytest_importable(python: str, project: Path) -> bool:
    return subprocess.run([python, "-c", "import pytest"], cwd=project, capture_output=True).returncode == 0


def wants_pytest(python: str, project: Path, test_files: list[str], commit: str) -> bool:
    if not pytest_importable(python, project):
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
    ran = re.search(r"^Ran (\d+) tests?", text, re.M) if runner == "unittest" else re.search(r"(\d+) (?:passed|failed)", text)
    if out.returncode != 0 and not failed and not errors:
        last = text.strip().splitlines()[-1] if text.strip() else ""
        errors.append(f"{runner} exited {out.returncode} before running the tests: {last}")
    elif not failed and not errors and (ran is None or int(ran.group(1)) == 0):
        errors.append(f"{runner} ran no tests from the listed files before running the tests: nothing was checked")
    return failed, errors, summary_line(text)


def test_name(test_id: str) -> str:
    """The function name a failure line carries, whichever runner printed it."""
    head = test_id.split(" (")[0]
    return head.split("::")[-1].split(".")[-1].split("[")[0]


def qualified(test_id: str) -> str:
    """One dotted spelling for a test, whichever runner or author wrote it.

    `test_x (pkg.mod.Case.test_x)` and `pkg/mod.py::Case::test_x[a]` both become `pkg.mod.Case.test_x`.
    """
    inner = re.search(r"\(([\w.]+)\)$", test_id)
    if inner:
        return inner.group(1)
    head = test_id.split("[")[0]
    return re.sub(r"\.py(?=::|$)", "", head).replace("::", ".").replace("/", ".")


def is_collection_error(error_id: str) -> bool:
    """An error that names a file or module rather than a test: nothing in it ran."""
    head = error_id.split(" (")[0]
    return "_FailedTest" in error_id or "before running the tests" in error_id or ("::" not in head and head.endswith(".py"))


def read_reasons(path: Path) -> tuple[list[dict], list[str]]:
    """Blocks of {tests, input, quote}, plus the problems that make a block unusable."""
    blocks: list[dict] = []
    problems: list[str] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        field = re.match(r"\s+(input|quote):\s*(.*)$", line)
        if field:
            if not blocks:
                problems.append(f"line {n}: `{field.group(1)}:` before any test line")
                continue
            blocks[-1][field.group(1)] = field.group(2).strip()
        elif line[0].isspace():
            problems.append(f"line {n}: indented line is neither `input:` nor `quote:`")
        elif blocks and not (blocks[-1]["input"] or blocks[-1]["quote"]):
            blocks[-1]["tests"].append(line.strip())
        else:
            blocks.append({"tests": [line.strip()], "input": "", "quote": "", "line": n})
    for block in blocks:
        quoted = re.search(r'"([^"]+)"', block["quote"])
        if not block["input"]:
            problems.append(f"line {block['line']}: block has no `input:` line")
        if not quoted or len(quoted.group(1).split()) < 4:
            problems.append(f"line {block['line']}: block has no `quote:` line holding a sentence in double quotes")
    return blocks, problems


def match_reasons(failed: list[str], blocks: list[dict]) -> tuple[dict[str, dict], list[str], list[dict]]:
    """Failing test -> block, failing tests no block names, blocks that name no failing test."""
    covered: dict[str, dict] = {}
    for block in blocks:
        for wanted in block["tests"]:
            exact = [t for t in failed if wanted == t or qualified(wanted) == qualified(t)]
            # A bare function name is shorthand for exactly one failing test; two matches need qualified ids.
            by_name = [t for t in failed if test_name(t) == wanted] if not exact and "::" not in wanted and "." not in wanted else []
            for test_id in exact or (by_name if len(by_name) == 1 else []):
                covered.setdefault(test_id, block)
    uncovered = [t for t in failed if t not in covered]
    idle = [b for b in blocks if not any(covered.get(t) is b for t in covered)]
    return covered, uncovered, idle


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
        try:
            for rel in self.paths:
                target = self.project / rel
                if target.exists() and not target.is_file():
                    raise IsADirectoryError(f"{rel} is a directory in the working tree, so the earlier file cannot be written there")
                self.saved[rel] = target.read_bytes() if target.exists() else None
                for parent in reversed(target.parents):
                    if parent != self.project and self.project in parent.parents and not parent.exists():
                        parent.mkdir()
                        self.made_dirs.append(parent)
                target.write_bytes(git(self.project, "show", f"{self.commit}:{rel}", binary=True).stdout)
        except BaseException:
            # Python skips __exit__ when __enter__ raises, so put back what was already replaced.
            self.restore()
            raise
        return self

    def restore(self):
        for rel, content in self.saved.items():
            target = self.project / rel
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        for d in reversed(self.made_dirs):
            shutil.rmtree(d, ignore_errors=True)

    def __exit__(self, *exc):
        self.restore()
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", required=True, help="commit whose test files run against the working tree")
    parser.add_argument("--project", type=Path, default=None, help="a path inside the repository (default: cwd)")
    parser.add_argument("--python", default=None, help="interpreter that has the project's dependencies (default: the project's .venv, else python on PATH)")
    parser.add_argument("--reasons", type=Path, default=None, help="file of allowed failures: test lines, then indented input: and quote: lines per block")
    parser.add_argument("--report-only", action="store_true", help="print the report and exit 0 whatever the result")
    args = parser.parse_args(argv)
    blocks: list[dict] = []
    if args.reasons is not None:
        if not args.reasons.is_file():
            print(f"preserve: --reasons {args.reasons} is not a file", file=sys.stderr)
            return 2
        blocks, problems = read_reasons(args.reasons)
        if problems:
            print(f"preserve: {args.reasons} is not a usable reasons file", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 2

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
        print(f"preserve: nothing to preserve, {commit[:10]} holds no Python test files. The gate is satisfied; a project tested in "
              "another language runs the start commit's test files with its own runner by hand, under the same policy.")
        return 0
    runner = "pytest" if wants_pytest(python, project, test_files, commit) else "unittest"
    try:
        with InPlace(project, commit, test_files + support):
            failed, errors, summary = run_tests(python, project, test_files, runner)
            nothing_ran = not failed and any("ran no tests" in e or "NO TESTS RAN" in e for e in errors)
            if runner == "unittest" and nothing_ran and pytest_importable(python, project):
                # Function-style tests with no pytest marker: unittest finds nothing, pytest runs them.
                runner = "pytest"
                failed, errors, summary = run_tests(python, project, test_files, runner)
    except OSError as exc:
        print(f"preserve: could not write the earlier test files into place, working tree restored: {exc}", file=sys.stderr)
        return 2

    print(f"preserve: {len(test_files)} test file(s) from {commit[:10]} run in place with {runner} against the working tree")
    if summary:
        print(f"  {summary}")
    # A test that raises because the code now rejects its input is an ERROR to the runner and a
    # failure to the policy, so a block may cover it. A file that could not run is never covered.
    waivable = failed + [e for e in errors if not is_collection_error(e)]
    covered, uncovered, idle = match_reasons(waivable, blocks) if blocks else ({}, waivable, [])
    uncovered += [e for e in errors if e not in waivable]
    for name in failed[:MAX_LISTED]:
        block = covered.get(name)
        print(f"  FAILED {name}" + (f"\n         reason: input {block['input']}; quote {block['quote']}" if block else ""))
    for name in errors[:MAX_LISTED]:
        block = covered.get(name)
        print(f"  ERROR  {name}" + (f"\n         reason: input {block['input']}; quote {block['quote']}" if block else ""))
    hidden = len(failed) + len(errors) - MAX_LISTED
    if hidden > 0:
        print(f"  ... {hidden} more")
    if errors:
        print("  An ERROR is a test that raised instead of asserting, or could not run (import, fixture, or collection).")
        print(f"  Ran with {python}; pass --python <interpreter> if the project's dependencies live elsewhere.")
    for block in idle:
        print(f"  Reasons block at line {block['line']} names no failing test: {', '.join(block['tests'])}")
    if blocks and uncovered:
        print(f"  {len(uncovered)} test(s) have no reason; each needs a code fix or its own block in {args.reasons}.")
        return 0 if args.report_only else 1
    if blocks and covered:
        print(f"  {len(covered)} test(s) waived, each with an input and a quoted sentence in {args.reasons}. Carry the blocks into the reply.")
        return 0
    if failed or errors:
        print("  Each failure needs either a code fix or the playbook's allowed reason before the commit.")
        return 0 if args.report_only else 1
    print("  All earlier tests still pass unedited.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
