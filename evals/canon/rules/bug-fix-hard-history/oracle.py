"""Close the grouped-command bypass in the shell parser that the GitHub and
working-directory policies share, without the splitting that git history
reverted."""
import json
from pathlib import PurePosixPath

from shared import OracleError, apply_diff, run_jobs

PARSER = "omnigent/policies/builtins/_shell.py"
PACKAGES = ("omnigent/policies", "omnigent/policies/builtins")
PINNED = ("tests/policies/builtins/test_github.py", "tests/policies/builtins/test_working_dir.py",
          "tests/policies/builtins/test_shell_nesting.py")
HELPERS = "tests/policies/builtins/helpers.py"
# These need pydantic, which the image lacks. A stub stands in, so the pinned
# tests that build policies through the engine fail on every tree alike.
STUB = '''class _Stub:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("stubbed: needs pydantic")

    def __class_getitem__(cls, item):
        return cls


def __getattr__(name):
    return type(name, (_Stub,), {})
'''
STUBBED = ("omnigent/policies/function.py", "omnigent/policies/registry.py", "omnigent/policies/types.py",
           "omnigent/policies/base.py", "omnigent/spec/types.py")
EMPTY = ("omnigent/__init__.py", "omnigent/policies/__init__.py", "omnigent/policies/builtins/__init__.py",
         "omnigent/spec/__init__.py", "tests/__init__.py", "tests/policies/__init__.py",
         "tests/policies/builtins/__init__.py")
PYTEST = '''import contextlib
import re


class Param:
    def __init__(self, values):
        self.values = values


def param(*values, **kwargs):
    return Param(values)


class _Mark:
    def __getattr__(self, name):
        def mark(*args, **kwargs):
            if len(args) == 1 and not kwargs and callable(args[0]):
                args[0].__dict__.setdefault("pytestmark", []).append((name, (), {}))
                return args[0]

            def apply(function):
                function.__dict__.setdefault("pytestmark", []).append((name, args, kwargs))
                return function
            return apply
        return mark


mark = _Mark()


@contextlib.contextmanager
def raises(expected, match=None):
    try:
        yield
    except expected as exc:
        if match is not None and not re.search(match, str(exc)):
            raise AssertionError(f"{exc!r} does not match {match!r}")
    else:
        raise AssertionError(f"did not raise {expected.__name__}")
'''
RUNNER = '''import asyncio, importlib, inspect, io, itertools, json, sys
import pytest

failures = []
out = sys.stdout
sys.stdout = io.StringIO()


def calls(function):
    grids = []
    for name, args, kwargs in reversed(getattr(function, "pytestmark", [])):
        if name != "parametrize":
            continue
        names = [part.strip() for part in args[0].split(",")] if isinstance(args[0], str) else list(args[0])
        rows = []
        for row in args[1]:
            row = row.values if isinstance(row, pytest.Param) else row
            rows.append(dict(zip(names, row if len(names) > 1 else (row,))))
        grids.append(rows)
    if not grids:
        return [("", {})]
    return [(f"[{index}]", {key: value for part in combo for key, value in part.items()})
            for index, combo in enumerate(itertools.product(*grids))]


for name in sys.argv[1:]:
    try:
        module = importlib.import_module(name)
    except BaseException as exc:
        failures.append(f"{name} does not import: {type(exc).__name__}")
        continue
    for key, value in vars(module).items():
        if not (key.startswith("test") and inspect.isfunction(value) and value.__module__ == name):
            continue
        for suffix, kwargs in calls(value):
            try:
                result = value(**kwargs)
                if inspect.iscoroutine(result):
                    asyncio.run(result)
            except BaseException:
                failures.append(f"{name}::{key}{suffix} failed")
out.write(json.dumps(failures))
'''
# The reported push, the same wrappers around a cd the working-directory policy
# gates through the same parser, the forms git history says a splitter let
# through (brace expansion, an escaped quote, an apostrophe in a comment), and
# wrapped commands that were allowed before and must stay allowed.
GROUPED = r'''from omnigent.policies.builtins.github import github_policy
from omnigent.policies.builtins.working_dir import block_working_dir_changes
from tests.policies.builtins.helpers import tool_call_event

OURS = "https://github.com/acme/storefront.git"
FORK = "https://github.com/jdoe/storefront-fork.git"


def github(command):
    policy = github_policy(write_repos=["acme/storefront"], write_branches=["main"])
    result = policy(tool_call_event("Bash", {"command": command}))
    return "ALLOW" if result is None else result["result"]


def working_dir(command):
    policy = block_working_dir_changes(allowed_dirs=["/workspace"])
    result = policy(tool_call_event("Bash", {"command": command}))
    return "ALLOW" if result is None else result["result"]


def test_parenthesized_push_to_a_fork_is_denied():
    assert github(f"(git push {FORK} main)") == "DENY"


def test_subshell_push_to_a_fork_is_denied():
    assert github(f"( git push {FORK} main )") == "DENY"


def test_brace_group_push_to_a_fork_is_denied():
    assert github(f"{{ git push {FORK} main; }}") == "DENY"


def test_process_substitution_push_to_a_fork_is_denied():
    assert github(f"cat <(git push {FORK} main)") == "DENY"


def test_subshell_cd_outside_the_workspace_is_denied():
    assert working_dir("( cd /etc )") == "DENY"


def test_brace_group_cd_outside_the_workspace_is_denied():
    assert working_dir("{ cd /etc; }") == "DENY"


def test_brace_expansion_cannot_add_a_branch():
    assert github(f"git push {OURS} main{{,}} release") == "DENY"


def test_brace_list_of_branches_is_denied():
    assert github(f"git push {OURS} {{main,release}}") == "DENY"


def test_escaped_quote_does_not_hide_a_push():
    assert github(f'echo \\" ; git push {FORK} main') == "DENY"


def test_apostrophe_in_a_comment_does_not_hide_a_push():
    assert github(f"# it's done\ngit push {FORK} main") == "DENY"


def test_subshell_push_to_our_main_is_allowed():
    assert github(f"( git push {OURS} main )") == "ALLOW"


def test_subshell_cd_inside_the_workspace_is_allowed():
    assert working_dir("( cd /workspace/app && make )") == "ALLOW"
'''


def policy_tree(checkout, changed):
    """The policy modules as the diff leaves them, with stubs for the modules
    that need pydantic, and the pinned test modules from the checkout."""
    tree = {}
    for package in PACKAGES:
        for path in sorted((checkout / package).glob("*.py")):
            tree[path.relative_to(checkout).as_posix()] = path.read_text(encoding="utf-8")
    for path, data in changed.items():
        if data is not None and path.endswith(".py") and PurePosixPath(path).parent.as_posix() in PACKAGES:
            tree[path] = data.decode("utf-8")
    for path, data in changed.items():
        if data is None and path in tree:
            del tree[path]
    tree.update({path: (checkout / path).read_text(encoding="utf-8") for path in (*PINNED, HELPERS)})
    tree.update({path: STUB for path in STUBBED})
    tree.update({path: "" for path in EMPTY})
    tree.update({"pytest.py": PYTEST, "_runner.py": RUNNER, "grouped_commands.py": GROUPED})
    return tree


def check_subshell_push(answer, workspace):
    """Runs the pinned policy test modules, never the agent's edited copies,
    on the checkout and on the tree the diff leaves. A pinned test counts only
    when it passes on the checkout. The held grouped-command cases run on the
    diff's tree."""
    changed = apply_diff(workspace.checkout, workspace.diff)
    if changed.get(PARSER, b"") is None:
        return [f"the diff deletes {PARSER}"]
    pinned = [path.removesuffix(".py").replace("/", ".") for path in PINNED]
    trees = {"pinned": policy_tree(workspace.checkout, {}), "answer": policy_tree(workspace.checkout, changed)}
    jobs = [{"tree": "pinned", "argv": ["python3", "_runner.py", *pinned], "timeout": 60},
            {"tree": "answer", "argv": ["python3", "_runner.py", *pinned, "grouped_commands"], "timeout": 60}]
    results = run_jobs(trees, jobs)
    for result in results:
        if result["rc"] != 0:
            raise OracleError(f"the test runner stopped (exit {result['rc']}): {result['stderr'].strip()[-300:]}")
    before, after = (json.loads(result["stdout"]) for result in results)
    return [failure for failure in after if failure not in before]


CHECKS = {"subshell-push": check_subshell_push}
