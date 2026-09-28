"""Make the zsh script work as an autoloaded fpath file without breaking the
eval install that git history once broke."""
from pathlib import PurePosixPath

from shared import apply_diff, plain_test_failures

MODULE = "hermes_cli/completion.py"
PINNED = "tests/hermes_cli/test_completion.py"
# The image has no zsh, so these read the generated script's top level: the
# lines outside any function body, each with whether an if, case, or && on it
# tests funcstack, zsh_eval_context or ZSH_EVAL_CONTEXT, compstate, or $0,
# which tell an autoload call apart from an eval. They need a top-level compdef and a top-level call
# to _hermes that such a guard covers, but they cannot tell which branch a
# guard takes, so an inverted guard passes.
INSTALLS = r'''import argparse
import re

from hermes_cli.completion import generate_zsh

GUARD = re.compile(r"funcstack|zsh_eval_context|ZSH_EVAL_CONTEXT|compstate|\$\{?0\b")
STATEMENT = r"(?:^|[;&|{(]|\b(?:then|else|do))\s*"
CALL = re.compile(STATEMENT + r"_hermes(?=\s|;|$)")
REGISTER = re.compile(STATEMENT + r"compdef\s+_hermes\s+hermes\b")


def parser():
    top = argparse.ArgumentParser(prog="hermes")
    top.add_argument("-p", "--profile", help="Profile name")
    sub = top.add_subparsers(dest="command")
    sub.add_parser("chat", help="Interactive chat with the agent")
    sub.add_parser("gateway", help="Messaging gateway").add_subparsers(dest="gateway_command").add_parser("start", help="Start")
    sub.add_parser("profile", help="Manage profiles").add_subparsers(dest="profile_command").add_parser("use", help="Switch")
    return top


def top_level(script):
    depth, blocks, lines = 0, [], []
    for raw in script.splitlines():
        code = re.sub(r"(^|\s)#.*", r"\1", re.sub(r"'[^']*'", "''", raw))
        opened = depth
        depth += code.count("{") - code.count("}")
        if opened or depth:
            continue
        head = code.strip()
        if re.match(r"(if|case)\b", head) and not re.search(r"\b(fi|esac)\s*;?\s*$", head):
            blocks.append(bool(GUARD.search(code)))
        elif re.match(r"elif\b", head) and blocks:
            blocks[-1] = blocks[-1] or bool(GUARD.search(code))
        lines.append((code, any(blocks) or bool(GUARD.search(code))))
        if re.match(r"(fi|esac)\b", head) and blocks:
            blocks.pop()
    return lines


SCRIPT = generate_zsh(parser())
TOP = top_level(SCRIPT)


def test_autoloaded_file_opens_with_its_compdef_tag():
    assert SCRIPT.splitlines()[0].strip() == "#compdef hermes"


def test_sourced_script_registers_the_completer():
    assert any(REGISTER.search(code) for code, _ in TOP)


def test_autoloaded_file_runs_the_completer_on_first_call():
    assert any(CALL.search(code) for code, _ in TOP)


def test_sourced_script_does_not_run_the_completer():
    assert not any(CALL.search(code) and not guarded for code, guarded in TOP)
'''


def check_zsh_first_tab(answer, workspace):
    """Runs the pinned test module, never the agent's edited copy, plus the
    install checks against the completion module the diff leaves."""
    changed = apply_diff(workspace.checkout, workspace.diff)
    if changed.get(MODULE, b"") is None:
        return [f"the diff deletes {MODULE}"]
    sources = {MODULE: (workspace.checkout / MODULE).read_bytes()}
    sources.update({path: data for path, data in changed.items()
                    if data is not None and PurePosixPath(path).parent.as_posix() == "hermes_cli" and path.endswith(".py")
                    and not path.endswith("__init__.py")})
    tree = {path: data.decode("utf-8") for path, data in sources.items()}
    tree[PINNED] = (workspace.checkout / PINNED).read_text(encoding="utf-8")
    tree.update({"hermes_cli/__init__.py": "", "tests/__init__.py": "", "tests/hermes_cli/__init__.py": "",
                 "zsh_install.py": INSTALLS})
    return plain_test_failures(tree, [PINNED.removesuffix(".py").replace("/", "."), "zsh_install"])


CHECKS = {"zsh-first-tab": check_zsh_first_tab}
