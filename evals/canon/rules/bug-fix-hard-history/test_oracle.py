import difflib
import importlib.util
import json
import unittest

from check import RULES, grade
from shared import Workspace

RULE, CASE = "bug-fix-hard-history", "subshell-push"
_spec = importlib.util.spec_from_file_location("canon_workspace_bug_fix_hard_history", RULES.parent / "workspace.py")
workspace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workspace)
OMNIGENT = "02969a131c72d74c00c5800d8e82ae831f8ec5e5"
PARSER = "omnigent/policies/builtins/_shell.py"
PINNED_SPLIT = '    parts = re.split(r"&&|\\|\\||[;|\\n&]", outer)\n'
# What #7999 shipped first and then reverted: a splitter that tracks quotes and
# splits on grouping characters outside them.
QUOTE_AWARE_SPLIT = '''    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(outer):
        ch = outer[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\\"":
            quote = ch
            buf.append(ch)
        elif outer.startswith(("&&", "||"), i):
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        elif ch in ";|\\n&(){}":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
'''
REPORTED = [
    "grouped_commands::test_parenthesized_push_to_a_fork_is_denied failed",
    "grouped_commands::test_subshell_push_to_a_fork_is_denied failed",
    "grouped_commands::test_brace_group_push_to_a_fork_is_denied failed",
    "grouped_commands::test_process_substitution_push_to_a_fork_is_denied failed",
    "grouped_commands::test_subshell_cd_outside_the_workspace_is_denied failed",
    "grouped_commands::test_brace_group_cd_outside_the_workspace_is_denied failed",
]
SPAWNED = "tests.policies.builtins.test_github::test_shell_process_spawning_utility_surfaces_the_push"
BRACE_EXPANSION = "grouped_commands::test_brace_expansion_cannot_add_a_branch failed"
BRACE_LIST = "grouped_commands::test_brace_list_of_branches_is_denied failed"
ESCAPED_QUOTE = "grouped_commands::test_escaped_quote_does_not_hide_a_push failed"
APOSTROPHE = "grouped_commands::test_apostrophe_in_a_comment_does_not_hide_a_push failed"


def sample_workspace(diff):
    root = RULES / RULE / "cases" / CASE
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    checkout, _ = workspace.reference_checkout(spec)
    return Workspace(checkout, diff)


def sample_diff(name):
    return (RULES / RULE / "cases" / CASE / "samples" / name).read_text(encoding="utf-8")


def diff_of(path, old, new):
    lines = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}"))
    return f"diff --git a/{path} b/{path}\n" + lines


def pinned(path):
    return sample_workspace("").checkout.joinpath(path).read_text(encoding="utf-8")


class NeedsOmnigentHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not workspace.has_history(workspace.mirror_path("omnigent", True), OMNIGENT):
            raise unittest.SkipTest(f"needs the history of omnigent {OMNIGENT}; run workspace.py fetch omnigent {OMNIGENT} --history")


class SubshellPushTests(NeedsOmnigentHistory):
    def test_stripping_grouping_in_the_shared_parser_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace(sample_diff("good.diff"))), [])

    def test_splitting_on_grouping_characters_breaks_brace_expansion_and_quoted_code(self):
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff"))),
                         [f"{SPAWNED}[2] failed", f"{SPAWNED}[3] failed", f"{SPAWNED}[4] failed", BRACE_EXPANSION, BRACE_LIST])

    def test_quote_aware_splitting_hides_pushes_the_pinned_tests_miss(self):
        source = pinned(PARSER)
        self.assertEqual(source.count(PINNED_SPLIT), 1)
        diff = diff_of(PARSER, source, source.replace(PINNED_SPLIT, QUOTE_AWARE_SPLIT))
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(diff)),
                         [BRACE_EXPANSION, BRACE_LIST, ESCAPED_QUOTE, APOSTROPHE])

    def test_patching_only_the_github_policy_leaves_the_other_wrappers_open(self):
        self.assertEqual(grade(RULE, CASE, "bad-symptom.md", workspace=sample_workspace(sample_diff("bad-symptom.diff"))),
                         REPORTED[1:])

    def test_no_change_fails_every_wrapped_command(self):
        self.assertEqual(grade(RULE, CASE, "good.md", workspace=sample_workspace("")), REPORTED)

    def test_deleting_a_pinned_test_module_does_not_hide_its_failures(self):
        path = "tests/policies/builtins/test_github.py"
        text = pinned(path)
        removal = f"diff --git a/{path} b/{path}\ndeleted file mode 100644\n" + "".join(
            difflib.unified_diff(text.splitlines(keepends=True), [], f"a/{path}", "/dev/null"))
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(sample_diff("bad.diff") + removal)),
                         [f"{SPAWNED}[2] failed", f"{SPAWNED}[3] failed", f"{SPAWNED}[4] failed", BRACE_EXPANSION, BRACE_LIST])

    def test_a_diff_that_deletes_the_parser_fails(self):
        text = pinned(PARSER)
        diff = f"diff --git a/{PARSER} b/{PARSER}\ndeleted file mode 100644\n" + "".join(
            difflib.unified_diff(text.splitlines(keepends=True), [], f"a/{PARSER}", "/dev/null"))
        self.assertEqual(grade(RULE, CASE, "bad.md", workspace=sample_workspace(diff)), [f"the diff deletes {PARSER}"])


if __name__ == "__main__":
    unittest.main()
