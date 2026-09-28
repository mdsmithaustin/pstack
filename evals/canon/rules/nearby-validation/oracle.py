"""Fix the reported bug without breaking the module's other pinned tests."""
from pathlib import PurePosixPath

from shared import apply_diff, plain_test_failures

MODULE = "hermes_cli/input_sanitize.py"
PINNED = ("tests/hermes_cli/test_input_sanitize.py", "tests/hermes_cli/test_cli_bracketed_paste_sanitizer.py")
# The second pinned module imports the sanitizer through cli.py, whose real
# imports need the full dependency set. This re-export is all it reads.
CLI_SHIM = "from hermes_cli.input_sanitize import strip_leaked_bracketed_paste_wrappers as _strip_leaked_bracketed_paste_wrappers\n"
REPORTED = '''from hermes_cli.input_sanitize import sanitize_user_prompt_text, strip_leaked_bracketed_paste_wrappers


def test_opening_marker_glued_to_a_typed_word():
    raw = 'logs[200~Traceback (most recent call last):\\n  File "app.py", line 3[201~'
    assert strip_leaked_bracketed_paste_wrappers(raw) == 'logsTraceback (most recent call last):\\n  File "app.py", line 3'


def test_glued_paste_followed_by_more_typing():
    raw = "check this output[200~ValueError: bad input[201~ please"
    assert sanitize_user_prompt_text(raw) == "check this outputValueError: bad input please"


def test_two_glued_pastes():
    assert strip_leaked_bracketed_paste_wrappers("a[200~x[201~ and b[200~y[201~") == "ax and by"
'''


def check_paste_markers(answer, workspace):
    """Runs the pinned test modules, never the agent's edited copies, plus the
    reported cases against the source the diff leaves."""
    changed = apply_diff(workspace.checkout, workspace.diff)
    if changed.get(MODULE, b"") is None:
        return [f"the diff deletes {MODULE}"]
    sources = {MODULE: (workspace.checkout / MODULE).read_bytes()}
    sources.update({path: data for path, data in changed.items()
                    if data is not None and PurePosixPath(path).parent.as_posix() == "hermes_cli" and path.endswith(".py")
                    and not path.endswith("__init__.py")})
    tree = {path: data.decode("utf-8") for path, data in sources.items()}
    tree.update({path: (workspace.checkout / path).read_text(encoding="utf-8") for path in PINNED})
    tree.update({"hermes_cli/__init__.py": "", "tests/__init__.py": "", "tests/hermes_cli/__init__.py": "",
                 "cli.py": CLI_SHIM, "reported_paste.py": REPORTED})
    modules = [path.removesuffix(".py").replace("/", ".") for path in PINNED]
    return plain_test_failures(tree, [*modules, "reported_paste"])


CHECKS = {"paste-markers": check_paste_markers}
