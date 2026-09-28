import difflib
import importlib.util
import json
import os
import pty
import re
import select
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from check import RULES, grade
from shared import Workspace

RULE, CASE = "bug-fix-spawn-step", "zsh-first-tab"
_spec = importlib.util.spec_from_file_location("canon_workspace_bug_fix_spawn_step", RULES.parent / "workspace.py")
workspace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workspace)
HERMES = "130b8f2c5dbca93a81aa396dd2ba44420d78f6f0"
MODULE = "hermes_cli/completion.py"
PINNED_TAIL = '}}\n\ncompdef _hermes hermes\n"""'
TAG = "zsh_install::test_autoloaded_file_opens_with_its_compdef_tag failed"
REGISTERS = "zsh_install::test_sourced_script_registers_the_completer failed"
FIRST_CALL = "zsh_install::test_autoloaded_file_runs_the_completer_on_first_call failed"
SOURCED_RUNS = "zsh_install::test_sourced_script_does_not_run_the_completer failed"
GUARDED = 'if [[ "${{funcstack[1]}}" == _hermes ]]; then\n    _hermes "$@"\nelse\n    compdef _hermes hermes\nfi'
# Each tail replaces the script's last line. The zsh columns are what a real
# zsh 5.9 did: first TAB lists subcommands from an fpath file, first TAB lists
# them after eval, and eval prints nothing.
VARIANTS = {
    "pinned": ("compdef _hermes hermes", [FIRST_CALL], (False, True, True)),
    "unguarded call": ('_hermes "$@"', [REGISTERS, SOURCED_RUNS], (True, False, False)),
    "funcstack guard": (GUARDED, [], (True, True, True)),
    "call and register, unguarded": ('compdef _hermes hermes\n_hermes "$@"', [SOURCED_RUNS], (True, True, False)),
    "register then guarded call": ('compdef _hermes hermes\n[[ "${{funcstack[1]}}" == _hermes ]] && _hermes "$@"', [], (True, True, True)),
    "zsh_eval_context guard": ('if [[ ${{zsh_eval_context[-1]}} == loadautofunc ]]; then\n    _hermes "$@"\nelse\n'
                               '    compdef _hermes hermes\nfi', [], (True, True, True)),
    "ZSH_EVAL_CONTEXT guard": ('if [[ $ZSH_EVAL_CONTEXT == *loadautofunc ]]; then\n    _hermes "$@"\nelse\n'
                               '    compdef _hermes hermes\nfi', [], (True, True, True)),
    # A known gap: a guard on the prompt-expanded function name works in zsh
    # but names none of the recognized parameters.
    "function name guard": ('if [[ ${{(%):-%N}} == _hermes ]]; then\n    _hermes "$@"\nelse\n'
                            '    compdef _hermes hermes\nfi', [SOURCED_RUNS], (True, True, True)),
    "argzero guard": ('if [[ $0 == _hermes ]]; then\n    _hermes "$@"\nelse\n    compdef _hermes hermes\nfi', [], (True, True, True)),
    # A known gap: the structure passes, but the inverted test breaks both installs.
    "inverted guard": (GUARDED.replace("==", "!="), [], (False, False, False)),
}


def sample_workspace(diff):
    root = RULES / RULE / "cases" / CASE
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    checkout, _ = workspace.reference_checkout(spec)
    return Workspace(checkout, diff)


def sample_diff(name):
    return (RULES / RULE / "cases" / CASE / "samples" / name).read_text(encoding="utf-8")


def pinned_source():
    return sample_workspace("").checkout.joinpath(MODULE).read_text(encoding="utf-8")


def variant_source(tail):
    source = pinned_source()
    return source.replace(PINNED_TAIL, '}}\n\n' + tail + '\n"""')


def diff_to(source):
    lines = "".join(difflib.unified_diff(pinned_source().splitlines(keepends=True), source.splitlines(keepends=True),
                                         f"a/{MODULE}", f"b/{MODULE}"))
    return f"diff --git a/{MODULE} b/{MODULE}\n" + lines if lines else ""


HISTORY_READY = workspace.has_history(workspace.mirror_path("hermes", True), HERMES)
NEEDS_MIRROR = f"needs the history of hermes {HERMES}; run workspace.py fetch hermes {HERMES} --history"


@unittest.skipUnless(HISTORY_READY, NEEDS_MIRROR)
class ZshFirstTabTests(unittest.TestCase):
    def test_guarded_call_passes_the_pinned_module_and_both_installs(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(sample_diff("good.diff"))), [])

    def test_unguarded_call_breaks_the_sourced_install(self):
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff"))), [REGISTERS, SOURCED_RUNS])

    def test_no_change_fails_only_the_first_call(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace("")), [FIRST_CALL])

    def test_calling_and_registering_unguarded_runs_the_completer_when_sourced(self):
        diff = diff_to(variant_source('compdef _hermes hermes\n_hermes "$@"'))
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(diff)), [SOURCED_RUNS])

    def test_dropping_the_compdef_tag_fails_the_autoload_tag(self):
        source = variant_source(GUARDED).replace('return f"""#compdef hermes\n', 'return f"""\n', 1)
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(diff_to(source))), [TAG])

    def test_a_diff_that_deletes_the_module_fails(self):
        diff = f"diff --git a/{MODULE} b/{MODULE}\ndeleted file mode 100644\n" + "".join(
            difflib.unified_diff(pinned_source().splitlines(keepends=True), [], f"a/{MODULE}", "/dev/null"))
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(diff)), [f"the diff deletes {MODULE}"])


def drive_zsh(script, mode):
    """(listed, quiet) from a fresh interactive zsh 5.9 with script installed
    as an fpath file or through eval: whether the first `hermes <TAB>` listed
    the subcommands, and whether installing printed nothing."""
    home = tempfile.mkdtemp()
    try:
        Path(home, "fp").mkdir()
        Path(home, "fp", "_hermes").write_text(script)
        Path(home, "script.zsh").write_text(script)
        install = ("fpath=(~/fp $fpath); autoload -Uz compinit; compinit -D" if mode == "fpath"
                   else 'autoload -Uz compinit; compinit -D; eval "$(cat ~/script.zsh)"')
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(home)
            os.execvpe("zsh", ["zsh", "-f", "-i"], {"HOME": home, "PATH": os.environ["PATH"], "TERM": "dumb"})
        try:
            read_until(fd, b"", 0.5)
            os.write(fd, install.encode() + b"; print M$((1+1))ARK\n")
            setup = read_until(fd, b"M2ARK", 10)
            os.write(fd, b"hermes \t")
            shown = read_until(fd, b"gateway", 3)
        finally:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        return b"gateway" in shown, b"can only be called" not in setup + shown
    finally:
        shutil.rmtree(home)


def read_until(fd, marker, seconds):
    out, end = b"", time.monotonic() + seconds
    while time.monotonic() < end and not (marker and marker in re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", out)):
        if select.select([fd], [], [], 0.1)[0]:
            try:
                out += os.read(fd, 65536)
            except OSError:
                break
    return re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", out)


def generated_script(source):
    """The script a patched completion.py prints. Only this file's own
    variants run here, on the host, never an agent's diff."""
    namespace = {"__name__": "completion_variant"}
    exec(compile(source, MODULE, "exec"), namespace)
    import argparse
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("chat", help="Chat")
    sub.add_parser("gateway", help="Gateway").add_subparsers(dest="gateway_command").add_parser("start", help="Start")
    return namespace["generate_zsh"](parser)


@unittest.skipUnless(HISTORY_READY, NEEDS_MIRROR)
@unittest.skipUnless(shutil.which("zsh"), "needs zsh on PATH to check the structural grade against real zsh")
class RealZshCalibrationTests(unittest.TestCase):
    """The grader's image has no zsh, so it grades the script's structure. This
    checks each structural verdict against what zsh does with the same script."""

    def test_structural_grade_and_real_zsh_for_each_variant(self):
        for name, (tail, failures, (fpath_lists, eval_lists, eval_quiet)) in VARIANTS.items():
            with self.subTest(name):
                source = variant_source(tail)
                self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(diff_to(source))), failures)
                script = generated_script(source)
                self.assertEqual(drive_zsh(script, "fpath")[0], fpath_lists)
                self.assertEqual(drive_zsh(script, "eval"), (eval_lists, eval_quiet))


if __name__ == "__main__":
    unittest.main()
