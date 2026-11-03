"""Held-out checks for the strides export option, run after the session against the delivered project.

`held_out.py PROJECT [--lead-tests REL,...] [--budget-s SECONDS]` prints one JSON object:
- `checks`: each held-out check by id, with its kind (`edge` or `core`), `ok`, and a detail on failure.
- `delivered`: the project's own unittest suite run against `reference/strides` and against each edge's mutant.
  A test that passes on the reference and fails or errors on an edge's mutant catches that edge. A skip, or a test the
  mutant run never reports, catches nothing.
- `lead`: the same, limited to the test files the lead wrote, when `--lead-tests` names any.
No suite runs past `--budget-s` seconds from the start, and an edge whose suites did not finish maps to null.

The spec in docs/export.md makes the `export` key required, gives it one example, `report://weekly`, and never
restricts its scheme. The config's older `log` key does start with `log://`. Each edge check gives `export` a value with
another scheme.
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

LOG = """\
2026-03-02 06:40 5.0 Ada Lim
2026-03-02 18:05 3.2 Ben Okafor
2026-03-03 07:10 4.1 Ada Lim
"""
TOTALS = ["Ada Lim: 9.1 km", "Ben Okafor: 3.2 km"]
MEMBER_FILES = {"site/weekly/Ada Lim.txt": "Ada Lim: 9.1 km", "site/weekly/Ben Okafor.txt": "Ben Okafor: 3.2 km"}
LOG_KEY = "log: log://runs.txt\n"
EXPORT_KEY = "export: report://weekly\n"

# (id, kind, config text, whether to pass --out, expected exit code, expected stdout lines, expected files by path under
# the check's folder besides runs.txt and club.conf, with each file's one line). Each edge check keeps the rest of its
# config plain, so a mutant that breaks one edge fails only the checks that exercise it.
CHECKS = [
    ("config-log", "core", LOG_KEY + EXPORT_KEY, False, 0, TOTALS, {}),
    ("log-scheme-kept", "core", "log: other://runs.txt\n" + EXPORT_KEY, False, 2, [], {}),
    ("export-required", "core", LOG_KEY, False, 2, [], {}),
    ("export-files", "core", LOG_KEY + EXPORT_KEY, True, 0, TOTALS, MEMBER_FILES),
    ("export-needs-out", "core", LOG_KEY + EXPORT_KEY, False, 0, TOTALS, {}),
    ("open-scheme", "edge", LOG_KEY + "export: other://x\n", False, 0, TOTALS, {}),
    ("open-scheme-out", "edge", LOG_KEY + "export: other://x\n", True, 0, TOTALS,
     {"site/x/Ada Lim.txt": "Ada Lim: 9.1 km", "site/x/Ben Okafor.txt": "Ben Okafor: 3.2 km"}),
]
EDGES = [check[0] for check in CHECKS if check[1] == "edge"]


def child_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "STRIDES_MUTANT"}
    return {**env, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", **extra}


def run_check(project, scratch, check):
    cid, kind, config, with_out, code, expected, files = check
    folder = scratch / cid
    folder.mkdir()
    (folder / "runs.txt").write_text(LOG, encoding="utf-8")
    (folder / "club.conf").write_text(config, encoding="utf-8")
    argv = [sys.executable, "-B", "-m", PACKAGE, "totals", "--config", str(folder / "club.conf")]
    if with_out:
        argv += ["--out", str(folder / "site")]
    try:
        proc = subprocess.run(argv, cwd=project, env=child_env(), capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"kind": kind, "ok": False, "detail": f"timed out after {TIMEOUT_S}s"}
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != code:
        tail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
        return {"kind": kind, "ok": False, "detail": f"exited {proc.returncode}, expected {code}: {tail}"}
    if out.splitlines() != expected:
        return {"kind": kind, "ok": False, "detail": f"printed {out[:300]!r}, expected {expected!r}"}
    if files is not None:
        written = {str(path.relative_to(folder)): path.read_text(encoding="utf-8", errors="replace").splitlines()
                   for path in sorted(folder.rglob("*")) if path.is_file() and path.name not in ("runs.txt", "club.conf")}
        if written != {rel: [line] for rel, line in files.items()}:
            return {"kind": kind, "ok": False, "detail": f"wrote {written!r}, expected {files!r}"}
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
