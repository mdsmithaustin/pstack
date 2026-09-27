"""Move the shared lint report loop without changing what either script prints."""
import ast

from shared import apply_diff, parse_python, plain_test_failures

FRAMEWORK = "dev/lint/_framework.py"
SCRIPTS = ("dev/lint/lint_no_skipped_tests.py", "dev/lint/lint_no_global_asyncio_patch.py")
PACKAGE = ("dev/__init__.py", "dev/lint/__init__.py", FRAMEWORK, *SCRIPTS)
SKIP_FOOTER = (
    "\nSkipped tests are invisible coverage loss. If a test can't pass, rewrite it for the current architecture "
    "or delete it. For genuine environmental gates (missing binary, platform), use ``@pytest.mark.skipif`` with a "
    "clear reason — this rule only flags unconditional ``skip``.\n"
)
ASYNCIO_FOOTER = (
    "\nPatching ``module.asyncio.sleep`` (or any other asyncio attribute via a dotted path that walks through the "
    "asyncio module) mutates the real asyncio module singleton, which leaks into every other test running in the "
    "same process (critical under pytest-xdist). Prefer adding a thin ``_sleep`` indirection in the production "
    "module and patching that, or replace the module's ``asyncio`` binding wholesale with a ``SimpleNamespace`` -- "
    "see the script docstring for Option A / Option B examples.\n"
)
HINT = "   hint: see dev/lint/lint_no_global_asyncio_patch.py docstring for correct shapes.\n"
SKIP_HITS = (
    "tests/test_skip_dirty.py:3: `@pytest.mark.skip` on `test_x`: skipped tests rot invisibly; rewrite or delete\n"
    "tests/test_skip_dirty.py:6: `pytestmark = pytest.mark.skip(...)` at module scope skips every test in the file\n"
)
HELD_OUTPUT = f'''import contextlib
import io
import os
import tempfile

from dev.lint import lint_no_global_asyncio_patch, lint_no_skipped_tests


def lines(*rows):
    return "".join(row + "\\n" for row in rows)


FILES = {{
    "tests/test_skip_dirty.py": lines("import pytest", "", "@pytest.mark.skip", "def test_x() -> None: ...", "", 'pytestmark = pytest.mark.skip(reason="wip")'),
    "tests/test_skip_clean.py": lines("import pytest, sys", '@pytest.mark.skipif(sys.platform == "win32", reason="x")', "def test_x() -> None: ..."),
    "tests/test_aio_dirty.py": "from unittest.mock import patch\\n\\npatch(\\"omnigent.tools.mcp.asyncio.sleep\\")\\nmonkeypatch.setattr(\\"omnigent.llms.client.asyncio.sleep\\", _fake)\\n",
    "tests/test_aio_clean.py": "patch(\\"omnigent.tools.mcp._sleep\\")\\n",
}}


def run(module, *paths):
    home = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            os.mkdir("tests")
            for path, text in FILES.items():
                with open(path, "w") as handle:
                    handle.write(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = module.main(["hook.py", *paths])
            return code, out.getvalue()
        finally:
            os.chdir(home)


def test_skip_report():
    assert run(lint_no_skipped_tests, "tests/test_skip_dirty.py", "tests/missing.py", "tests/test_skip_clean.py") == (1, {SKIP_HITS + SKIP_FOOTER!r})


def test_skip_report_repeats_a_repeated_path():
    assert run(lint_no_skipped_tests, "tests/test_skip_dirty.py", "tests/test_skip_dirty.py") == (1, {SKIP_HITS + SKIP_HITS + SKIP_FOOTER!r})


def test_skip_clean_is_silent():
    assert run(lint_no_skipped_tests, "tests/test_skip_clean.py") == (0, "")


def test_asyncio_report_keeps_a_hint_after_every_hit():
    expected = (
        'tests/test_aio_dirty.py:3: globally-clobbering asyncio patch detected: patch("omnigent.tools.mcp.asyncio.sleep")\\n'
        + {HINT!r}
        + 'tests/test_aio_dirty.py:4: globally-clobbering asyncio patch detected: monkeypatch.setattr("omnigent.llms.client.asyncio.sleep", _fake)\\n'
        + {HINT!r}
        + {ASYNCIO_FOOTER!r}
    )
    assert run(lint_no_global_asyncio_patch, "tests/test_aio_clean.py", "tests/test_aio_dirty.py") == (1, expected)


def test_asyncio_clean_skips_directories():
    assert run(lint_no_global_asyncio_patch, "tests/test_aio_clean.py", "tests") == (0, "")
'''


def main_loops(path, body):
    """Whether the module's main still holds its own loop."""
    mains = [node for node in parse_python(path, body).body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    return any(isinstance(node, (ast.For, ast.While)) for main in mains for node in ast.walk(main))


def check_lint_report_loop(answer, workspace):
    changed = apply_diff(workspace.checkout, workspace.diff)
    failures = [] if changed.get(FRAMEWORK) is not None else [f"{FRAMEWORK} is unchanged or deleted"]
    tree = {}
    for path in PACKAGE:
        data = changed[path] if path in changed else (workspace.checkout / path).read_bytes()
        if data is None:
            failures.append(f"the diff deletes {path}")
            continue
        tree[path] = data.decode("utf-8")
    tree.update({path: data.decode("utf-8") for path, data in changed.items()
                 if data is not None and path.startswith("dev/lint/") and path.endswith(".py")})
    failures += [f"{path} main still loops over its arguments" for path in SCRIPTS if path in tree and main_loops(path, tree[path])]
    if failures:
        return failures
    return plain_test_failures({**tree, "held_output.py": HELD_OUTPUT}, ["held_output"])


CHECKS = {"lint-report-loop": check_lint_report_loop}
