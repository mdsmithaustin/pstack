"""Runs named test files of the checkout at /work against the image's /deps
and prints {test id: passed, failed, or skipped} as JSON. Python files run
under pytest, and may name a pytest node id; other files run under vitest in the nearest directory with a
package.json. A file that reports no tests counts as one failure."""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WORK = Path("/work")
DEPS = Path("/deps")


def link_node_modules():
    for directory, names, _ in os.walk(DEPS):
        if "node_modules" not in names:
            names[:] = [name for name in names if name != ".venv"]
            continue
        names[:] = [name for name in names if name not in {"node_modules", ".venv"}]
        modules = Path(directory) / "node_modules"
        target = WORK / modules.parent.relative_to(DEPS) / "node_modules"
        if not target.parent.is_dir() or target.exists():
            continue
        # A real directory of links, since vite writes its temp files into node_modules.
        target.mkdir()
        for entry in modules.iterdir():
            (target / entry.name).symlink_to(entry)


def pytest_results(files):
    report = Path("/tmp/pytest.xml")
    subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "--junitxml", str(report), *files],
                   cwd=WORK, stdout=sys.stderr, check=False)
    results = {}
    for case in ET.parse(report).iter("testcase") if report.is_file() else []:
        outcome = "passed"
        if case.find("skipped") is not None:
            outcome = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        label = f"{case.get('classname')}::{case.get('name')}" if case.get("classname") else case.get("name")
        results[label] = "failed" if outcome == "failed" or results.get(label) == "failed" else outcome
    return results


def vitest_results(package, files):
    report = Path("/tmp/vitest.json")
    subprocess.run([str(WORK / package / "node_modules" / ".bin" / "vitest"), "run", "--reporter=json",
                    f"--outputFile={report}", *[os.path.relpath(path, package) for path in files]],
                   cwd=WORK / package, stdout=sys.stderr, check=False)
    results = {}
    for suite in json.loads(report.read_text())["testResults"] if report.is_file() else []:
        path = Path(suite["name"]).relative_to(WORK).as_posix()
        for test in suite["assertionResults"]:
            status = {"passed": "passed", "failed": "failed"}.get(test["status"], "skipped")
            results[f"{path}::{test['fullName']}"] = status
        if suite["status"] == "failed" and not suite["assertionResults"]:
            results[path] = "failed"
    return results


def package_of(path):
    for parent in Path(path).parents:
        if (WORK / parent / "package.json").is_file():
            return parent.as_posix()
    return "."


link_node_modules()
tests = sys.argv[1:]
python = [test for test in tests if test.split("::")[0].endswith(".py")]
results = pytest_results(python) if python else {}
packages = {}
for path in tests:
    if path not in python:
        packages.setdefault(package_of(path), []).append(path)
for package, paths in packages.items():
    results.update(vitest_results(package, paths))
for test in tests:
    path = test.split("::")[0]
    if not any(label.startswith((path, path.removesuffix(".py").replace("/", "."))) for label in results):
        results[test] = "failed"
json.dump(results, sys.stdout)
