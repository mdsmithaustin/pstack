#!/usr/bin/env python3
"""Run the test files that existed at a commit, unedited, against the working tree.

The agent that changes code also edits the tests that disagree with it. This script keeps the
earlier tests out of its reach: it writes the start commit's test files into place, runs them
against the current code, and restores their saved working-tree contents. Automatic selection runs
exactly those test files; --command delegates selection to the repository task. The files run in
place because tests find the project through their own location (`Path(__file__).parent / ".."`,
fixture directories).

Automatic selection uses pytest configuration and function/import hints, then runtime class
evidence for undecided suites. Undecided modules load under unittest's module names and are reused
if pytest is selected. Automatic pytest collection retains the baseline's python_files,
python_functions, and python_classes settings through the selected pytest's configuration discovery.
Without an explicit baseline python_files setting, the broader Python filename patterns still apply.
Use --command for a repository task that needs different import naming or third-party collection
plugins without those hints.

    preserve.py --since <commit> [--project <root>] [--python <exe>] [--reasons <file>] [--report-only]

Exit 0 when the selected tests pass, all failures have allowed reasons, or there are no earlier
Python tests. Exit 1 when a failure is uncovered, tests cannot run, or no test executes, including
an all-skipped suite. Exit 2 when the arguments, overlay, or recovery are unusable. --report-only suppresses
test-result failures; invalid arguments, refs, and overlay setup still fail.

Use --command <argv...> as the last argument when the repository has its own test task. It runs
without a shell from the repository root, with baseline files restored. The task owns test selection
and must provide unittest or pytest execution evidence. A command that proves no test execution fails.
This strict mode cannot be combined with --reasons. For example:

    preserve.py --since <commit> --command mise run gate-test

Commands whose executable resolves to the selected --python executable, followed by supported Python
options and -m unittest, use native result data to distinguish skipped methods from skipped subtests:

    preserve.py --since <commit> --python <python> --command <python> -m unittest discover -s tests

The adapter preserves the executable, interpreter options, unittest selection, normal test output,
and native exit status. It launches a Python wrapper, so process argv and import-tracing diagnostics
can reveal the helper. Supported standalone Python options are -B, -E, -I, -O, -OO, -P, -q, -s, -S,
-u, -v, -vv, -b, -bb, -d, and -R. -W and -X accept attached or separate values.

Other commands and unsupported invocation forms use output summaries. A positive conservative
execution count is sufficient. When unittest skip counts leave execution ambiguous, the command
fails with a diagnostic naming the direct form above. Summary text alone cannot distinguish a skipped
method from an executed method with skipped subtests.

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

The overlay first saves original test and support-file bytes and modes in a private
preserve-backup directory under this worktree's Git directory. Before any baseline write, preflight
refuses selected files with multiple hard links and exits 2. Selected overlay targets must be
independent regular files. Find the Git directory with
`git rev-parse --absolute-git-dir`. Another overlay refuses a pending backup. Successful
restoration removes the backup; incomplete restoration retains it.

On POSIX, INT, TERM, and HUP stop the owned command group before restoration. After successful
restoration, the CLI exits with 128 plus the signal number. Failed cleanup or restoration exits 2
and retains the backup. SIGKILL cannot run cleanup, so the selected command may still be active.
Stop the original command before recovery. Recovery refuses a recorded live owner or command group
and never signals processes.

Use the backup directory printed by the pending-overlay error:

    preserve.py --project <root> --recover <printed-backup-directory>

Recovery accepts only that worktree's backup. It restores saved files and modes, then removes the
backup. Repeating successful recovery exits 0 without changing files. If restoration had completed
but backup removal failed, recovery retries removal without replaying restoration over later edits.
Recovery retains ambiguous or invalid evidence for inspection. It rejects --since, --python,
--reasons, --report-only, and --command. Run normal preservation again after recovery.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TEST_DIRS = {"test", "tests"}
MAX_LISTED = 120
PYTEST_CONFIGS = ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
UNITTEST_RESULTS = '''\
class UnittestResults(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = []
        self.skipped_tests = []
        self.current = None

    def startTest(self, test):
        super().startTest(test)
        self.current = test
        self.started.append(str(test))

    def stopTest(self, test):
        super().stopTest(test)
        self.current = None

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if test is self.current:
            self.skipped_tests.append(str(test))

    def evidence(self):
        return dict(failed=[str(test) for test, _ in self.failures],
                    errors=[str(test) for test, _ in self.errors],
                    started=self.started, skipped=self.skipped_tests,
                    ran=len(self.started) - len(self.skipped_tests))
'''
TEST_RUNNER = '''\
import inspect
import json
import sys
import unittest
from pathlib import Path


''' + UNITTEST_RESULTS + '''

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


report = Path(sys.argv[1])
runner, configuration, files = sys.argv[2], Path(sys.argv[3]), sys.argv[4:]
data = {"runner": "pytest" if runner == "pytest" else "unittest", "failed": [], "errors": [], "ran": 0}
report.write_text(json.dumps(data))
if runner == "optional":
    try:
        import pytest
    except Exception:
        runner = "auto"
    else:
        runner = "pytest"

modules = []
if runner == "auto":
    class Imports(unittest.TestLoader):
        def loadTestsFromModule(self, module, *, pattern=None):
            modules.append(module)
            return self.suiteClass()

    imports = Imports()
    names = [path[:-12] if path.endswith("/__init__.py") else path[:-3] for path in files]
    import_errors = imports.loadTestsFromNames([path.replace("/", ".") for path in names])
    requires_pytest = False
    for module in modules:
        pending = list(vars(module).items())
        seen = set()
        while pending:
            name, value = pending.pop()
            marked = getattr(value, "__test__", False) is True
            if (name.startswith("test") or marked) and callable(value) and not isinstance(value, type) and getattr(value, "__test__", True):
                requires_pytest = True
            if not (name.startswith("Test") or marked) or not isinstance(value, type) or issubclass(value, unittest.TestCase):
                continue
            if id(value) in seen or inspect.isabstract(value) or not getattr(value, "__test__", True):
                continue
            if value.__init__ is not object.__init__ or value.__new__ is not object.__new__:
                continue
            seen.add(id(value))
            pending.extend((name, getattr(value, name)) for name in dir(value))
    runner = "pytest" if requires_pytest and not imports.errors else "unittest"

data["runner"] = runner
report.write_text(json.dumps(data))
if runner == "pytest":
    import pytest

    for module in modules:
        path = Path(module.__file__).resolve()
        parts = [] if path.name == "__init__.py" else [path.stem]
        parent = path.parent
        while (parent / "__init__.py").is_file():
            parts.insert(0, parent.name)
            parent = parent.parent
        if parts:
            sys.modules.setdefault(".".join(parts), module)
    results = Results()
    baseline = pytest.Config.fromdictargs({}, [*[str(configuration / path) for path in files], "--noconftest", "-o", "addopts="])
    naming = []
    for name in ("python_files", "python_functions", "python_classes"):
        patterns = baseline.getini(name)
        if name == "python_files" and name not in baseline.inicfg:
            patterns = ["test*.py", "*_test.py", "*_tests.py"]
        naming.extend(["-o", name + "=" + " ".join(patterns)])
    baseline._ensure_unconfigure()
    status = pytest.main(["-q", "-p", "no:cacheprovider", "-rfE", "-o", "addopts=", "--maxfail=0",
                          *naming, *files], plugins=[results])
    data.update(failed=results.failed, errors=results.errors, ran=results.ran,
                incomplete=len(results.finished) != results.collected or results.deselected > 0)
else:
    suite = unittest.TestSuite([import_errors, *(unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules)])
    result = unittest.TextTestRunner(resultclass=UnittestResults).run(suite)
    status = int(not result.wasSuccessful())
    data.update(result.evidence())
report.write_text(json.dumps(data))
sys.exit(status)
'''
UNITTEST_COMMAND = '''\
import json
import runpy
import sys
import unittest
from pathlib import Path

''' + UNITTEST_RESULTS + '''
report = Path(sys.argv[1])
report.write_text(json.dumps(dict(failed=[], errors=[], ran=0)))

class CommandResults(UnittestResults):
    def stopTestRun(self):
        super().stopTestRun()
        report.write_text(json.dumps(self.evidence()))

unittest.TextTestRunner.resultclass = CommandResults
sys.argv = ["-m", *sys.argv[2:]]
if not getattr(sys.flags, "safe_path", sys.flags.isolated):
    sys.path[0] = str(Path.cwd())
runpy.run_module("unittest", run_name="__main__", alter_sys=True)
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


def baseline_pytest_configs(project: Path, test_files: list[str], commit: str) -> dict[str, bytes]:
    parents = {parent for path in test_files for parent in Path(path).parents}
    entries = [entry for entry in git(project, "ls-tree", "-r", "-z", commit).stdout.split("\0") if entry and not entry.startswith("120000 ")]
    paths = [entry.split("\t", 1)[1] for entry in entries]
    return {path: git(project, "show", f"{commit}:{path}", binary=True).stdout
            for path in paths if Path(path).name in PYTEST_CONFIGS and Path(path).parent in parents}


def select_runner(project: Path, test_files: list[str], commit: str) -> str:
    configs = {path: source.decode(errors="ignore") for path, source in baseline_pytest_configs(project, test_files, commit).items()}
    for name in PYTEST_CONFIGS:
        if name not in configs and (project / name).is_file():
            configs[name] = (project / name).read_text(errors="ignore")
    if any(Path(name).name in ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini") for name in configs) or (project / "conftest.py").exists():
        return "pytest"
    for name, source in configs.items():
        if Path(name).name in ("tox.ini", "setup.cfg"):
            ini = configparser.ConfigParser(interpolation=None)
            ini.read_string(source)
            if ini.has_section("pytest" if Path(name).name == "tox.ini" else "tool:pytest"):
                return "pytest"
        if Path(name).name == "pyproject.toml" and "[tool.pytest" in source:
            return "pytest"
    has_pytest_import = False
    for path in test_files:
        source = git(project, "show", f"{commit}:{path}", binary=True).stdout
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                return "pytest"
        has_pytest_import = has_pytest_import or any(
            isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "pytest" for alias in node.names)
            or isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None and node.module.split(".")[0] == "pytest"
            for node in ast.walk(module)
        )
    return "optional" if has_pytest_import else "auto"


def direct_unittest(command: list[str], python: str, project: Path) -> int | None:
    paths = []
    for name in (command[0], python):
        found = str(project / name) if os.sep in name else shutil.which(name)
        if not found:
            return None
        paths.append(Path(found).resolve())
    if paths[0] != paths[1]:
        return None
    index = 1
    while index < len(command):
        option = command[index]
        if option == "-m":
            return index if command[index + 1:index + 2] == ["unittest"] else None
        if option in ("-W", "-X"):
            index += 2
        elif option in {"-B", "-E", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v", "-vv", "-b", "-bb", "-d", "-R"} or option.startswith(("-W", "-X")):
            index += 1
        else:
            return None
    return None


def run_tests(python: str, files: list[str], runner: str, overlay: InPlace,
              command: list[str] | None = None) -> tuple[str, list[str], list[str], str]:
    with tempfile.TemporaryDirectory(prefix="preserve-") as isolated:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(Path(isolated) / "pycache"))
        env.pop("PYTEST_ADDOPTS", None)
        report = Path(isolated) / "results.json"
        structured_command = direct_unittest(command, python, overlay.project) if runner == "command" else None
        if runner != "command":
            configuration = Path(isolated) / "configuration"
            configuration.mkdir()
            configs = baseline_pytest_configs(overlay.project, files, overlay.commit)
            for name, source in configs.items():
                target = configuration / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source)
            if not configs:
                (configuration / "pytest.ini").write_text("[pytest]\n")
            for path in files:
                target = configuration / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            cmd = [python, "-c", TEST_RUNNER, str(report), runner, str(configuration), *files]
        elif structured_command is not None:
            cmd = [*command[:structured_command], "-c", UNITTEST_COMMAND, str(report), *command[structured_command + 2:]]
        else:
            cmd = command
        out = overlay.run(cmd, env=env)
        text = out.stdout + out.stderr
        if runner != "command" or structured_command is not None:
            results = json.loads(report.read_text()) if report.exists() else {"runner": "pytest" if runner == "pytest" else "unittest", "failed": [], "errors": [], "ran": 0}
            if runner != "command":
                runner = results["runner"]
            failed, errors, ran = results["failed"], results["errors"], results["ran"]
            if results.get("incomplete"):
                errors.append("pytest stopped before running the tests to completion: the baseline suite was incomplete")
        else:
            failed = re.findall(r"^FAIL: (\S+ \([\w.]+\).*)$", text, re.M)
            errors = re.findall(r"^ERROR: (\S+ \([\w.]+\).*)$", text, re.M)
            counts = re.findall(r"^Ran (\d+) tests?", text, re.M)
            skipped = re.findall(r"^(?:OK|FAILED) \([^\n]*\bskipped=(\d+)", text, re.M)
            ran = sum(map(int, counts)) - sum(map(int, skipped))
            if counts and skipped and ran <= 0:
                errors.append("command has ambiguous unittest execution evidence before running the tests: "
                              "the summary cannot distinguish skipped methods from skipped subtests; "
                              "use --python <interpreter> --command <same-interpreter> -m unittest <selection> for structured evidence")
                ran = None
            if not counts:
                ran = sum(map(int, re.findall(r"(\d+) (?:passed|failed)", text)))
    if out.returncode not in (0, 1) or (out.returncode != 0 and not failed and not errors):
        last = text.strip().splitlines()[-1] if text.strip() else ""
        errors.append(f"{runner} exited {out.returncode} before running the tests: {last}")
    if ran is not None and ran <= 0:
        errors.append(f"{runner} ran no tests from the listed files before running the tests: nothing was checked")
    return runner, failed, errors, summary_line(text)


def test_name(test_id: str) -> str:
    head = test_id.split(" (")[0]
    return head.split("::")[-1].split(".")[-1].split("[")[0]


def qualified(test_id: str) -> str:
    """One dotted spelling for a test, whichever runner or author wrote it.

    `test_x (pkg.mod.Case.test_x)` and `pkg/mod.py::Case::test_x` both become `pkg.mod.Case.test_x`. A parameter
    suffix stays, so `test_x[a]` and `test_x[b]` are two tests and each failing case needs its own name.
    """
    inner = re.match(r"\S+ \(([\w.]+)\)(.*)$", test_id)
    if inner:
        return inner.group(1) + inner.group(2)
    head = re.split(r"\[| \(", test_id, maxsplit=1)[0]
    return re.sub(r"\.py(?=::|$)", "", head).replace("::", ".").replace("/", ".") + test_id[len(head):]


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


class Interrupted(BaseException):

    def __init__(self, signum: int):
        self.signum = signum


class InPlace:

    def __init__(self, project: Path, commit: str, paths: list[str]):
        self.project, self.commit, self.paths = project, commit, paths
        admin = Path(git(project, "rev-parse", "--absolute-git-dir").stdout.strip())
        self.backup = admin / "preserve-backup"
        self.saved: dict[str, dict] = {}
        self.made_dirs: list[str] = []
        self.command: int | None = None
        self.restored = False
        self.handlers: dict[int, object] = {}

    def run(self, cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        reader, writer = os.pipe()
        launcher = ("import os, sys; fd = int(sys.argv[1]); ready = os.read(fd, 1); os.close(fd); "
                    "sys.exit(125) if ready != b'1' else os.execvpe(sys.argv[2], sys.argv[2:], os.environ)")
        with os.fdopen(reader, "rb") as ready_read, os.fdopen(writer, "wb", buffering=0) as ready_write:
            with subprocess.Popen([sys.executable, "-c", launcher, str(reader), *cmd], cwd=self.project, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  start_new_session=True, pass_fds=(reader,)) as out:
                try:
                    self.command = out.pid
                    self.save_manifest()
                    ready_write.write(b"1")
                    ready_write.close()
                    while out.poll() is None:
                        try:
                            out.communicate(timeout=0.1)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    ready_write.close()
                    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGHUP})
                    try:
                        try:
                            os.killpg(out.pid, signal.SIGTERM)
                        except (ProcessLookupError, PermissionError):
                            pass
                        try:
                            out.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                        try:
                            os.killpg(out.pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            pass
                        stdout, stderr = out.communicate()
                        deadline = time.monotonic() + 2
                        while True:
                            try:
                                os.killpg(out.pid, 0)
                            except ProcessLookupError:
                                break
                            except PermissionError:
                                pass
                            if time.monotonic() >= deadline:
                                raise OSError(f"command process group {out.pid} did not stop; backup retained")
                            time.sleep(0.01)
                        self.command = None
                        self.save_manifest()
                    finally:
                        signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
        return subprocess.CompletedProcess(cmd, out.returncode, stdout, stderr)

    def save_manifest(self):
        manifest = {"version": 1, "project": str(self.project), "owner": os.getpid(), "restored": self.restored, "saved": self.saved,
                    "made_dirs": self.made_dirs, "command": self.command}
        temporary = self.backup / "manifest.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.backup / "manifest.json")
        for path in (self.backup, self.backup.parent):
            directory = os.open(path, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    @staticmethod
    def interrupt(signum, frame):
        for watched in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(watched, signal.SIG_IGN)
        raise Interrupted(signum)

    def restore_handlers(self):
        for signum, handler in self.handlers.items():
            signal.signal(signum, handler)
        self.handlers.clear()

    def __enter__(self):
        try:
            self.backup.mkdir(mode=0o700)
        except FileExistsError:
            raise OSError(f"pending preservation backup at {self.backup}; stop its command and use --recover {self.backup}")
        try:
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                self.handlers[signum] = signal.signal(signum, self.interrupt)
            for index, rel in enumerate(self.paths):
                target = self.project / rel
                if target.is_symlink() or any(p.is_symlink() for p in target.parents if self.project in p.parents):
                    raise OSError(f"{rel} is, or sits under, a symlink in the working tree; the overlay never writes through a link")
                if target.exists() and not target.is_file():
                    raise IsADirectoryError(f"{rel} is a directory in the working tree, so the earlier file cannot be written there")
                if target.exists() and target.stat().st_nlink > 1:
                    raise OSError(f"{rel} has a hard link in the working tree; the overlay never writes through a shared inode")
                entry = {"backup": str(index) if target.exists() else None,
                         "mode": target.stat().st_mode & 0o7777 if target.exists() else None}
                if entry["backup"] is not None:
                    with (self.backup / entry["backup"]).open("wb") as handle:
                        handle.write(target.read_bytes())
                        handle.flush()
                        os.fsync(handle.fileno())
                self.saved[rel] = entry
                for parent in reversed(target.parents):
                    if parent != self.project and self.project in parent.parents and not parent.exists():
                        relative = str(parent.relative_to(self.project))
                        if relative not in self.made_dirs:
                            self.made_dirs.append(relative)
            self.save_manifest()
            for rel in self.paths:
                target = self.project / rel
                for parent in reversed(target.parents):
                    if parent != self.project and self.project in parent.parents and not parent.exists():
                        parent.mkdir()
                target.write_bytes(git(self.project, "show", f"{self.commit}:{rel}", binary=True).stdout)
        except BaseException:
            try:
                if (self.backup / "manifest.json").exists():
                    self.restore()
                else:
                    shutil.rmtree(self.backup)
            finally:
                self.restore_handlers()
            raise
        return self

    def restore(self):
        if self.command is not None:
            raise OSError(f"command process group {self.command} may still be running; backup retained at {self.backup}")
        if not self.saved and not self.backup.exists():
            return
        handlers = {signum: signal.signal(signum, signal.SIG_IGN)
                    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            self.restore_files()
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)

    def restore_files(self):
        if self.restored:
            self.remove_backup()
            return
        problems = []
        for rel, entry in self.saved.items():
            target = self.project / rel
            try:
                if target.is_symlink() or any(p.is_symlink() for p in target.parents if self.project in p.parents):
                    raise OSError(f"{rel} is, or sits under, a symlink")
                if entry["backup"] is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    content = (self.backup / entry["backup"]).read_bytes()
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                        temporary = Path(handle.name)
                        try:
                            handle.write(content)
                            handle.flush()
                            os.fsync(handle.fileno())
                            os.fchmod(handle.fileno(), entry["mode"])
                        except BaseException:
                            temporary.unlink(missing_ok=True)
                            raise
                    try:
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
            except OSError as exc:
                problems.append(f"{rel}: {exc}")
        for d in reversed(self.made_dirs):
            try:
                target = self.project / d
                if target.is_symlink() or any(p.is_symlink() for p in target.parents if self.project in p.parents):
                    raise OSError(f"{d} is, or sits under, a symlink")
                target.rmdir()
            except FileNotFoundError:
                pass
            except OSError as exc:
                problems.append(f"{d}: {exc}")
        if problems:
            raise OSError(f"working tree restoration incomplete; backup retained at {self.backup}: " + "; ".join(problems))
        self.restored = True
        self.save_manifest()
        self.remove_backup()

    def remove_backup(self):
        expected = {entry["backup"] for entry in self.saved.values() if entry["backup"] is not None}
        expected.update(("manifest.json", "manifest.tmp"))
        if any(path.name not in expected for path in self.backup.iterdir()):
            raise OSError(f"unexpected backup contents; restored working tree and backup retained at {self.backup}")
        for name in expected - {"manifest.json"}:
            (self.backup / name).unlink(missing_ok=True)
        (self.backup / "manifest.json").unlink()
        self.backup.rmdir()
        self.saved.clear()
        self.made_dirs.clear()

    def __exit__(self, *exc):
        try:
            self.restore()
        finally:
            self.restore_handlers()
        return False

    def recover(self, backup: Path):
        if backup.absolute() != self.backup or backup.is_symlink():
            raise OSError(f"recovery must use this worktree's backup directory: {self.backup}")
        if not self.backup.exists():
            return
        if not any(self.backup.iterdir()):
            self.backup.rmdir()
            return
        try:
            manifest_path = self.backup / "manifest.json"
            if manifest_path.is_symlink():
                raise ValueError("manifest is a symlink")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["version"] != 1 or manifest["project"] != str(self.project):
                raise ValueError("manifest belongs to a different project or version")
            restored = manifest["restored"]
            if type(restored) is not bool:
                raise ValueError("invalid restoration state")
            owner = manifest["owner"]
            if type(owner) is not int or owner <= 1:
                raise ValueError("invalid preservation process")
            try:
                os.kill(owner, 0)
            except ProcessLookupError:
                pass
            else:
                raise OSError(f"preservation process {owner} still exists; stop it before recovery")
            saved, made_dirs, command = manifest["saved"], manifest["made_dirs"], manifest["command"]
            if not isinstance(saved, dict) or not isinstance(made_dirs, list):
                raise ValueError("invalid saved paths")
            for index, (rel, entry) in enumerate(saved.items()):
                path = Path(rel)
                if path.is_absolute() or ".." in path.parts or ".git" in path.parts or not path.parts:
                    raise ValueError("saved path escapes the project")
                if entry["backup"] is not None:
                    content = self.backup / str(index)
                    if entry["backup"] != str(index) or content.is_symlink() or not (restored or content.is_file()):
                        raise ValueError("invalid backup file")
                    if type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o7777:
                        raise ValueError("invalid saved mode")
            for rel in made_dirs:
                path = Path(rel)
                if path.is_absolute() or ".." in path.parts or not path.parts or not any(path in Path(p).parents for p in saved):
                    raise ValueError("invalid created directory")
            if command is not None:
                if type(command) is not int or command <= 1:
                    raise ValueError("invalid command process group")
                try:
                    os.killpg(command, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise OSError(f"command process group {command} still exists; stop it before recovery")
            self.saved, self.made_dirs = saved, made_dirs
            self.restored = restored
        except (ValueError, KeyError, TypeError) as exc:
            raise OSError(f"invalid recovery manifest at {self.backup}: {exc}") from exc
        self.restore()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--since", help="commit whose test files run against the working tree")
    source.add_argument("--recover", type=Path, help="restore a pending backup after its selected command has stopped")
    parser.add_argument("--project", type=Path, default=None, help="a path inside the repository (default: cwd)")
    parser.add_argument("--python", default=None, help="interpreter with project dependencies (default: project .venv/bin/python, then venv/bin/python, then python on PATH, then the running interpreter)")
    parser.add_argument("--reasons", type=Path, default=None, help="file of allowed failures: test lines, then indented input: and quote: lines per block")
    parser.add_argument("--report-only", action="store_true", help="print test results and exit 0; invalid arguments, refs, and overlay setup still fail")
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="project test command, last argument; requires unittest or pytest execution summaries and forbids --reasons")
    args = parser.parse_args(argv)
    if args.recover is not None and (args.command is not None or args.reasons is not None or args.report_only or args.python is not None):
        parser.error("--recover cannot be combined with --command, --reasons, --report-only, or --python")
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

    if args.since is not None and args.since.strip().lower().replace("-", " ") in ("no commits", "none", "unborn"):
        print("preserve: nothing to preserve, the task started with no commits. The gate is satisfied; the step's own tests still have to pass.")
        return 0
    start = (args.project or Path.cwd()).resolve()
    top = git(start, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        print(f"preserve: {start} is not inside a git repository", file=sys.stderr)
        return 2
    project = Path(top.stdout.strip())
    if args.recover is not None:
        try:
            InPlace(project, "", []).recover(args.recover)
        except OSError as exc:
            print(f"preserve: {exc}", file=sys.stderr)
            return 2
        print("preserve: working tree restored from the pending backup")
        return 0
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
    try:
        with InPlace(project, commit, test_files + support) as overlay:
            runner = "command" if args.command is not None else select_runner(project, test_files, commit)
            runner, failed, errors, summary = run_tests(python, test_files, runner, overlay, args.command)
    except Interrupted as exc:
        print(f"preserve: interrupted by signal {exc.signum}; working tree restored", file=sys.stderr)
        return 128 + exc.signum
    except OSError as exc:
        print(f"preserve: could not run the earlier test files: {exc}", file=sys.stderr)
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
