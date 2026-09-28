"""Build the requested lint rule: its detection, suppression, standalone run, and registration."""
from shared import apply_diff, plain_test_failures

MODULE = "dev/lint/lint_no_debugger.py"
HELD_BEHAVIOR = '''import os
import re
import subprocess
import sys

FIXTURES = {
    "dirty.py": ["import os", "import pdb", "", "def f():", "    breakpoint()", "    pdb.set_trace()",
                 "import ipdb; ipdb.set_trace()", "from pudb import set_trace"],
    "clean.py": ['note = "call breakpoint() here"', "# pdb.set_trace()", "breakpoints = []", "pdb_path = 'x'",
                 "def set_trace_level(n):", "    return n"],
    "quiet.py": ["breakpoint()  # custom-lint: disable=no-debugger"],
}


def run(name):
    os.makedirs("fixtures", exist_ok=True)
    with open(f"fixtures/{name}", "w") as handle:
        handle.write("".join(row + "\\n" for row in FIXTURES[name]))
    proc = subprocess.run([sys.executable, "-m", "dev.lint.lint_no_debugger", f"fixtures/{name}"],
                          capture_output=True, text=True, timeout=30)
    lines = {int(match.group(1)) for match in re.finditer(rf"^\\S*fixtures/{re.escape(name)}:(\\d+):", proc.stdout, re.MULTILINE)}
    return proc.returncode, lines


def test_each_debugger_line_is_reported():
    assert run("dirty.py") == (1, {2, 5, 6, 7, 8})


def test_strings_comments_and_lookalike_names_pass():
    assert run("clean.py") == (0, set())


def test_disable_comment_silences_the_line():
    assert run("quiet.py") == (0, set())


def test_registered_after_the_existing_rules():
    from dev.lint import custom_lint

    names = [rule.name for rule in custom_lint.RULES]
    assert names[:2] == ["workspace-scoped-cache", "session-list-visibility"]
    assert "no-debugger" in names[2:]
    assert all(callable(rule.check) for rule in custom_lint.RULES)
'''


def check_no_debugger_lint(answer, workspace):
    changed = apply_diff(workspace.checkout, workspace.diff)
    if changed.get(MODULE) is None:
        return [f"{MODULE} is missing"]
    tree = {path.relative_to(workspace.checkout).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted((workspace.checkout / "dev" / "lint").glob("*.py"))}
    tree["dev/__init__.py"] = (workspace.checkout / "dev" / "__init__.py").read_text(encoding="utf-8")
    for path, data in changed.items():
        if path.startswith("dev/") and path.endswith(".py"):
            if data is None:
                tree.pop(path, None)
            else:
                tree[path] = data.decode("utf-8")
    return plain_test_failures({**tree, "held_behavior.py": HELD_BEHAVIOR}, ["held_behavior"])


CHECKS = {"no-debugger-lint": check_no_debugger_lint}
