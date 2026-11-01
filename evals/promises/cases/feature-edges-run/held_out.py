"""Held-out checks for the strides streaks command, run after the session against the delivered project.

`held_out.py PROJECT [--lead-tests REL,...] [--budget-s SECONDS]` prints one JSON object:
- `checks`: each held-out check by id, with its kind (`edge` or `core`), `ok`, and a detail on failure.
- `delivered`: the project's own unittest suite run against `reference/strides` and against each edge's mutant.
  A test that passes on the reference and fails or errors on an edge's mutant catches that edge. A skip, or a test the
  mutant run never reports, catches nothing.
- `lead`: the same, limited to the test files the lead wrote, when `--lead-tests` names any.
No suite runs past `--budget-s` seconds from the start, and an edge whose suites did not finish maps to null.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference" / "strides"
PACKAGE = "strides"
SKIP_TOP = {".git", ".claude", ".agents", ".codex", ".hermes", ".grok"}
TIMEOUT_S = 30
SUITE_TIMEOUT_S = 180

EXAMPLE = """\
2026-03-02 06:15 3.2 Ben Okafor
2026-03-02 06:40 5.0 Ada Lim
2026-03-03 07:10 4.1 Ada Lim
2026-03-03 19:00 3.0 Ben Okafor
2026-03-04 06:55 5.0 Ada Lim
2026-03-04 18:45 3.1 Ben Okafor
2026-03-05 06:50 6.3 Ada Lim
2026-03-07 07:00 4.0 Cleo Park
"""

# Both specs ask for `strides.streaks.longest_streaks(runs, min_days=3)` for the newsletter. This prints its pairs with
# the default threshold, then with the threshold in its second argument.
API_PROBE = """\
import json
import sys

from strides.log import read_runs
from strides.streaks import longest_streaks

runs = read_runs(sys.argv[1])
for pairs in (longest_streaks(runs), longest_streaks(runs, min_days=int(sys.argv[2]))):
    print(json.dumps([list(pair) for pair in pairs]))
"""

# (id, kind, command, log text, extra args, expected stdout lines). The command is a strides subcommand, or
# `longest_streaks` to run API_PROBE. Each edge check exercises one edge and keeps the rest of its log plain, so a
# mutant that breaks one edge fails only that check.
CHECKS = [
    ("example", "core", "streaks", EXAMPLE, ["--min-days", "2"], ["Ada Lim: 4", "Ben Okafor: 3"]),
    ("longest-stretch", "core", "streaks",
     "2026-03-01 06:00 5.0 Maya Chen\n2026-03-02 06:00 5.0 Maya Chen\n"
     "2026-03-05 06:00 5.0 Maya Chen\n2026-03-06 06:00 5.0 Maya Chen\n"
     "2026-03-07 06:00 5.0 Maya Chen\n2026-03-08 06:00 5.0 Maya Chen\n", [], ["Maya Chen: 4"]),
    ("month-boundary", "core", "streaks",
     "2026-02-27 06:00 5.0 Omar Said\n2026-02-28 06:00 5.0 Omar Said\n2026-03-01 06:00 5.0 Omar Said\n"
     "2026-03-02 06:00 5.0 Omar Said\n", [], ["Omar Said: 4"]),
    ("nobody-listed", "core", "streaks",
     "2026-03-02 06:00 5.0 Ada Lim\n2026-03-03 06:00 5.0 Ada Lim\n2026-03-02 07:00 4.0 Ben Okafor\n", [],
     ["no streaks"]),
    ("min-days-option", "core", "streaks",
     "2026-03-02 06:00 5.0 Ada Lim\n2026-03-03 06:00 5.0 Ada Lim\n2026-03-04 07:00 4.0 Ben Okafor\n"
     "2026-03-05 07:00 4.0 Ben Okafor\n2026-03-06 07:00 4.0 Ben Okafor\n",
     ["--min-days", "1"], ["Ben Okafor: 3", "Ada Lim: 2"]),
    ("totals-unchanged", "core", "totals", EXAMPLE, [],
     ["Ada Lim: 20.4 km", "Ben Okafor: 9.3 km", "Cleo Park: 4.0 km"]),
    ("api", "core", "longest_streaks",
     "2026-03-01 06:00 5.0 Maya Chen\n2026-03-02 06:00 5.0 Maya Chen\n2026-03-02 07:00 4.0 Ada Lim\n"
     "2026-03-03 06:00 5.0 Maya Chen\n2026-03-03 07:00 4.0 Ada Lim\n2026-03-04 06:00 5.0 Maya Chen\n", ["1"],
     ['[["Maya Chen", 4]]', '[["Maya Chen", 4], ["Ada Lim", 2]]']),
    ("boundary", "edge", "streaks",
     "2026-03-02 06:00 5.0 Ada Lim\n2026-03-03 06:00 5.0 Ada Lim\n2026-03-04 06:00 5.0 Ada Lim\n"
     "2026-03-02 07:00 4.0 Ben Okafor\n2026-03-03 07:00 4.0 Ben Okafor\n", [], ["Ada Lim: 3"]),
    ("empty", "edge", "streaks", "", [], ["no streaks"]),
    ("ties", "edge", "streaks",
     "2026-03-02 06:00 5.0 Noor Haddad\n2026-03-02 07:00 5.0 Ines Duarte\n"
     "2026-03-03 06:00 5.0 Noor Haddad\n2026-03-03 07:00 5.0 Ines Duarte\n"
     "2026-03-04 06:00 5.0 Noor Haddad\n2026-03-04 07:00 5.0 Ines Duarte\n"
     "2026-03-05 06:00 5.0 Noor Haddad\n2026-03-05 07:00 5.0 Ines Duarte\n"
     "2026-03-04 08:00 5.0 Theo Brandt\n2026-03-05 08:00 5.0 Theo Brandt\n2026-03-06 08:00 5.0 Theo Brandt\n"
     "2026-03-07 08:00 5.0 Theo Brandt\n2026-03-08 08:00 5.0 Theo Brandt\n", [],
     ["Theo Brandt: 5", "Noor Haddad: 4", "Ines Duarte: 4"]),
    ("casefold", "edge", "streaks",
     "2026-03-02 06:00 5.0 Jürgen Weiß\n2026-03-03 06:00 5.0 JÜRGEN WEISS\n2026-03-04 06:00 5.0 jürgen weiss\n"
     "2026-03-05 06:00 5.0 Jürgen Weiß\n", [], ["Jürgen Weiß: 4"]),
    ("same-day", "edge", "streaks",
     "2026-03-02 06:00 5.0 Ada Lim\n2026-03-02 18:00 3.0 Ada Lim\n2026-03-03 06:00 5.0 Ada Lim\n"
     "2026-03-04 06:00 5.0 Ada Lim\n2026-03-05 06:00 5.0 Ada Lim\n2026-03-02 07:00 4.0 Ben Okafor\n"
     "2026-03-02 19:00 4.0 Ben Okafor\n2026-03-03 07:00 4.0 Ben Okafor\n2026-03-03 19:00 4.0 Ben Okafor\n", [],
     ["Ada Lim: 4"]),
    ("out-of-order", "edge", "streaks",
     "2026-03-02 06:00 5.0 Ada Lim\n2026-03-05 06:00 5.0 Ada Lim\n2026-03-03 06:00 5.0 Ada Lim\n"
     "2026-03-04 06:00 5.0 Ada Lim\n", [], ["Ada Lim: 4"]),
]
EDGES = [check[0] for check in CHECKS if check[1] == "edge"]


def child_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "STRIDES_MUTANT"}
    return {**env, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", **extra}


def run_check(project, scratch, check):
    cid, kind, command, log, args, expected = check
    path = scratch / f"{cid}.log"
    path.write_text(log, encoding="utf-8")
    head = ["-c", API_PROBE] if command == "longest_streaks" else ["-m", PACKAGE, command]
    argv = [sys.executable, "-B", *head, str(path), *args]
    try:
        proc = subprocess.run(argv, cwd=project, env=child_env(), capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"kind": kind, "ok": False, "detail": f"timed out after {TIMEOUT_S}s"}
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
        return {"kind": kind, "ok": False, "detail": f"exited {proc.returncode}: {tail}"}
    if out.splitlines() != expected:
        return {"kind": kind, "ok": False, "detail": f"printed {out[:300]!r}, expected {expected!r}"}
    return {"kind": kind, "ok": True}


def copy_project(project, dest):
    """Copies the delivered project and swaps its package for the reference. Keeps the package's own test files, and each
    folder in the package that holds a test file, whole, so a nested test package keeps its support files."""
    def ignore(folder, names):
        top = Path(folder) == project
        return {n for n in names if n == "__pycache__" or (top and (n in SKIP_TOP or n == PACKAGE))}
    shutil.copytree(project, dest, ignore=ignore, symlinks=True)
    shutil.copytree(REFERENCE, dest / PACKAGE, ignore=shutil.ignore_patterns("__pycache__"))
    delivered = project / PACKAGE
    if delivered.is_dir():
        for test in delivered.glob("test*.py"):
            shutil.copyfile(test, dest / PACKAGE / test.name)
        for folder in delivered.iterdir():
            if folder.is_dir() and any(folder.rglob("test*.py")):
                shutil.copytree(folder, dest / PACKAGE / folder.name, ignore=shutil.ignore_patterns("__pycache__"), symlinks=True)


def run_suite(project, scratch, label, mutant, names, deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        return None
    root = scratch / f"suite-{label}"
    copy_project(project, root)
    out = scratch / f"suite-{label}.json"
    argv = [sys.executable, "-B", str(Path(__file__).resolve()), "--suite", str(root), str(out), *names]
    # Output goes to devnull because a process a test leaves running would hold a pipe open past the timeout.
    try:
        subprocess.run(argv, cwd=root, env=child_env(STRIDES_MUTANT=mutant), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=min(SUITE_TIMEOUT_S, left))
    except subprocess.TimeoutExpired:
        return None
    return json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None


def catches(project, scratch, label, names, deadline):
    """Maps each edge to the project's tests that pass on the reference and fail or error on that edge's mutant."""
    base = run_suite(project, scratch, f"{label}-reference", "", names, deadline)
    if base is None:
        return {"tests": 0, "passing_on_reference": 0, "caught": dict.fromkeys(EDGES),
                "error": "suite did not finish on the reference"}
    passing = sorted(t for t, outcome in base.items() if outcome == "pass")
    caught = {}
    for edge in EDGES:
        outcomes = run_suite(project, scratch, f"{label}-{edge}", edge, names, deadline)
        caught[edge] = None if outcomes is None else sorted(t for t in passing if outcomes.get(t) in ("fail", "error"))
    return {"tests": len(base), "passing_on_reference": len(passing), "caught": caught}


class Recorder(unittest.TestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = {}

    def addSuccess(self, test):
        self.outcomes.setdefault(test.id(), "pass")

    def addFailure(self, test, err):
        self.outcomes[test.id()] = "fail"

    def addError(self, test, err):
        self.outcomes[test.id()] = "error"

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = "skip"

    def addExpectedFailure(self, test, err):
        self.outcomes[test.id()] = "expected-failure"

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = "fail"

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.outcomes[test.id()] = "fail"


def suite_main(root, out, names):
    sys.path.insert(0, str(root))
    os.chdir(root)
    loader = unittest.TestLoader()
    if names:
        suite = unittest.TestSuite()
        for name in names:
            try:
                suite.addTests(loader.loadTestsFromName(name))
            except unittest.SkipTest:
                continue
    else:
        suite = loader.discover(str(root), pattern="test*.py", top_level_dir=str(root))
    result = Recorder()
    suite.run(result)
    Path(out).write_text(json.dumps(result.outcomes), encoding="utf-8")


def main(argv):
    if argv[:1] == ["--suite"]:
        suite_main(Path(argv[1]), argv[2], argv[3:])
        return 0
    parser = argparse.ArgumentParser(prog="held_out.py")
    parser.add_argument("project", type=Path)
    parser.add_argument("--lead-tests", type=lambda value: value.split(","), default=[])
    parser.add_argument("--budget-s", type=float, default=math.inf)
    args = parser.parse_args(argv)
    project, lead = args.project.resolve(), args.lead_tests
    deadline = time.monotonic() + args.budget_s
    with tempfile.TemporaryDirectory(prefix="strides-held-") as tmp:
        scratch = Path(tmp)
        report = {"checks": {check[0]: run_check(project, scratch, check) for check in CHECKS},
                  "delivered": catches(project, scratch, "delivered", [], deadline),
                  "lead_files": lead,
                  "lead": catches(project, scratch, "lead", [r[:-3].replace("/", ".") for r in lead], deadline) if lead else None}
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
