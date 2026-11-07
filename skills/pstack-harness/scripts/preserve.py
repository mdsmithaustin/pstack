#!/usr/bin/env python3
"""Run the test files that existed at a commit, unedited, against the working tree.

The agent that changes code also edits the tests that disagree with it. This script keeps the
earlier tests out of its reach: it writes the start commit's test files into place, runs exactly
those files against the current code, and restores whatever the working tree held, so a behavior
the earlier tests pinned cannot change silently. The files run in place because tests find the
project through their own location (`Path(__file__).parent / ".."`, fixture directories).

    preserve.py --since <commit> [--project <root>] [--python <exe>] [--reasons <file>] [--report-only]

Exit 0 when every earlier test passes or there are no earlier Python tests, 1 when any fails or
cannot run, and 2 when the arguments or overlay are unusable. --report-only suppresses test-result failures; invalid arguments, refs, and overlay setup still fail.

Use --command <argv...> as the last argument when the repository has its own test task. It runs
without a shell from the repository root, with baseline files restored. The task owns test selection
and must emit unittest or pytest execution summaries. A command that reports no executed tests fails.
This strict mode cannot be combined with --reasons. For example:

    preserve.py --since <commit> --command mise run gate-test

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
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_DIRS = {"test", "tests"}
MAX_LISTED = 120
PYTEST_RUNNER = '''\
import json
import sys
from pathlib import Path

import pytest


class Results:
    def __init__(self):
        self.failed = []
        self.errors = []
        self.finished = set()
        self.ran = 0
        self.collected = 0
        self.deselected = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and not report.skipped:
            self.ran += 1
        if report.when == "teardown":
            self.finished.add(report.nodeid)
        if report.failed:
            (self.failed if report.when == "call" else self.errors).append(report.nodeid)

    def pytest_collectreport(self, report):
        if report.failed:
            self.errors.append(f"collection failed before running the tests: {report.nodeid}")

    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_sessionfinish(self, session):
        self.collected = session.testscollected


results = Results()
status = pytest.main(sys.argv[2:], plugins=[results])
Path(sys.argv[1]).write_text(json.dumps({
    "failed": results.failed,
    "errors": results.errors,
    "ran": results.ran,
    "incomplete": len(results.finished) != results.collected or results.deselected > 0,
}))
sys.exit(status)
'''


def is_test_file(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if not name.endswith(".py") or name == "conftest.py":
        return False
    return any(p in TEST_DIRS for p in parts[:-1]) or name.startswith("test") or name.endswith(("_test.py", "_tests.py"))


def is_support_file(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if name == "conftest.py":
        return True
    return not name.endswith(".py") and any(p in TEST_DIRS for p in parts[:-1])


def git(project: Path, *args: str, check: bool = True, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=not binary, check=check)


def pytest_importable(python: str, project: Path) -> bool:
    return subprocess.run([python, "-c", "import pytest"], cwd=project, capture_output=True).returncode == 0


def wants_pytest(project: Path, test_files: list[str], commit: str) -> bool:
    if any((project / name).exists() for name in ("pytest.ini", "conftest.py", "tox.ini")):
        return True
    pyproject = project / "pyproject.toml"
    if pyproject.exists() and "[tool.pytest" in pyproject.read_text(errors="ignore"):
        return True
    for path in test_files:
        source = git(project, "show", f"{commit}:{path}", binary=True).stdout
        if b"import pytest" in source or b"from pytest " in source:
            return True
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test") for node in module.body):
            return True
    return False


def run_tests(python: str, project: Path, files: list[str], runner: str, command: list[str] | None = None) -> tuple[list[str], list[str], str]:
    with tempfile.TemporaryDirectory(prefix="preserve-") as isolated:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(Path(isolated) / "pycache"))
        env.pop("PYTEST_ADDOPTS", None)
        if runner == "pytest":
            report = Path(isolated) / "results.json"
            cmd = [python, "-c", PYTEST_RUNNER, str(report), "-q", "-p", "no:cacheprovider", "-rfE",
                   "-o", "addopts=", "--maxfail=0", "-o", "python_files=test*.py *_test.py *_tests.py", *files]
        else:
            cmd = command if command is not None else [python, "-m", "unittest", *files]
        out = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
        text = out.stdout + out.stderr
        if runner == "pytest":
            results = json.loads(report.read_text()) if report.exists() else {"failed": [], "errors": [], "ran": 0}
            failed, errors, ran = results["failed"], results["errors"], results["ran"]
            if results.get("incomplete"):
                errors.append("pytest stopped before running the tests to completion: the baseline suite was incomplete")
        else:
            failed = re.findall(r"^FAIL: (\S+ \([\w.]+\))", text, re.M)
            errors = re.findall(r"^ERROR: (\S+ \([\w.]+\))", text, re.M)
            counts = re.findall(r"^Ran (\d+) tests?", text, re.M)
            skipped = re.findall(r"^(?:OK|FAILED) \([^\n]*\bskipped=(\d+)", text, re.M)
            ran = sum(map(int, counts)) - sum(map(int, skipped))
            if runner == "command" and not counts:
                ran = sum(map(int, re.findall(r"(\d+) (?:passed|failed)", text)))
    if out.returncode not in (0, 1) or (out.returncode != 0 and not failed and not errors):
        last = text.strip().splitlines()[-1] if text.strip() else ""
        errors.append(f"{runner} exited {out.returncode} before running the tests: {last}")
    elif not failed and not errors and ran == 0:
        errors.append(f"{runner} ran no tests from the listed files before running the tests: nothing was checked")
    return failed, errors, summary_line(text)


def test_name(test_id: str) -> str:
    head = test_id.split(" (")[0]
    return head.split("::")[-1].split(".")[-1].split("[")[0]


def qualified(test_id: str) -> str:
    """One dotted spelling for a test, whichever runner or author wrote it.

    `test_x (pkg.mod.Case.test_x)` and `pkg/mod.py::Case::test_x` both become `pkg.mod.Case.test_x`. A parameter
    suffix stays, so `test_x[a]` and `test_x[b]` are two tests and each failing case needs its own name.
    """
    inner = re.search(r"\(([\w.]+)\)$", test_id)
    if inner:
        return inner.group(1)
    head, _, param = test_id.partition("[")
    return re.sub(r"\.py(?=::|$)", "", head).replace("::", ".").replace("/", ".") + (f"[{param}" if param else "")


def is_collection_error(error_id: str) -> bool:
    """An error that names a file or module rather than a test: nothing in it ran."""
    head = error_id.split(" (")[0]
    return "_FailedTest" in error_id or "before running the tests" in error_id or ("::" not in head and head.endswith(".py"))


def read_reasons(path: Path) -> tuple[list[dict], list[str]]:
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
        if not quoted or not quoted.group(1).strip():
            problems.append(f"line {block['line']}: block has no `quote:` line holding a sentence in double quotes")
    return blocks, problems


def match_reasons(failed: list[str], blocks: list[dict]) -> tuple[dict[str, dict], list[str], list[dict]]:
    covered: dict[str, dict] = {}
    for block in blocks:
        for wanted in block["tests"]:
            exact = [t for t in failed if wanted == t or qualified(wanted) == qualified(t)]
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

    def __init__(self, project: Path, commit: str, paths: list[str]):
        self.project, self.commit, self.paths = project, commit, paths
        self.saved: dict[str, bytes | None] = {}
        self.made_dirs: list[Path] = []

    def __enter__(self):
        try:
            for rel in self.paths:
                target = self.project / rel
                if target.is_symlink() or any(p.is_symlink() for p in target.parents if self.project in p.parents):
                    raise OSError(f"{rel} is, or sits under, a symlink in the working tree; the overlay never writes through a link")
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
    parser.add_argument("--report-only", action="store_true", help="print test results and exit 0; invalid arguments, refs, and overlay setup still fail")
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="project test command, last argument; requires unittest or pytest execution summaries and forbids --reasons")
    args = parser.parse_args(argv)
    if args.command is not None and (not args.command or args.reasons is not None):
        parser.error("--command needs an argument vector and cannot be combined with --reasons")
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

    if args.since.strip().lower().replace("-", " ") in ("no commits", "none", "unborn"):
        print("preserve: nothing to preserve, the task started with no commits. The gate is satisfied; the step's own tests still have to pass.")
        return 0
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

    # -z keeps non-ASCII paths unquoted; a 120000 entry is a symlink, which the overlay never writes.
    entries = [e for e in git(project, "ls-tree", "-r", "-z", commit).stdout.split("\0") if e]
    listed = [e.split("\t", 1)[1] for e in entries if not e.startswith("120000 ")]
    test_files = [p for p in listed if is_test_file(p)]
    support = [p for p in listed if is_support_file(p)]
    if not test_files:
        print(f"preserve: nothing to preserve, {commit[:10]} holds no Python test files. The gate is satisfied; a project tested in "
              "another language runs the start commit's test files with its own runner by hand, under the same policy.")
        return 0
    runner = "command" if args.command is not None else "pytest" if wants_pytest(project, test_files, commit) else "unittest"
    try:
        with InPlace(project, commit, test_files + support):
            failed, errors, summary = run_tests(python, project, test_files, runner, args.command)
            nothing_ran = not failed and any("ran no tests" in e or "NO TESTS RAN" in e for e in errors)
            if runner == "unittest" and nothing_ran and pytest_importable(python, project):
                runner = "pytest"
                failed, errors, summary = run_tests(python, project, test_files, runner)
    except OSError as exc:
        print(f"preserve: could not write the earlier test files into place, working tree restored: {exc}", file=sys.stderr)
        return 2

    if runner == "command":
        print(f"preserve: {len(test_files)} baseline Python test file(s) restored from {commit[:10]}; the project command owns test selection")
    else:
        print(f"preserve: {len(test_files)} test file(s) from {commit[:10]} run in place with {runner} against the working tree")
    if summary:
        print(f"  {summary}")
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
    print("  The selected project test command passed with baseline files restored." if runner == "command" else "  All earlier tests still pass unedited.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
