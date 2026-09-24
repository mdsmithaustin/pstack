import difflib
import json
import sys
import unittest

from check import RULES, grade
from shared import Workspace

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE, CASE = "route-codebase-design", "pricing-modules"
GOOD = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text(encoding="utf-8")


class PricingModulesTests(unittest.TestCase):
    def test_deep_module_with_in_memory_adapter_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_facade_over_the_shallow_modules_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "6 test(s) on the shallow modules kept: test_amount_becomes_cents_and_currency_uppercases, test_fetch_reads_the_price_json, "
                "test_missing_currency_is_invalid, test_negative_amount_is_invalid, test_put_then_get_returns_the_price, test_unknown_sku_misses",
                "no in-memory adapter for the pricing service",
                "tests/test_cache.py mocks instead of using an adapter",
                "tests/test_fetcher.py mocks instead of using an adapter",
                "tests/test_mapper.py mocks instead of using an adapter",
                "tests/test_service.py mocks instead of using an adapter",
            ],
        )

    def test_changed_output_fails_the_pin(self):
        changed = GOOD.replace('raw["currency"].upper()', 'raw["currency"]')

        self.assertEqual(
            grade(RULE, CASE, text=changed),
            ["checkout, quotes, or catalog export behave differently against the same pricing responses", "final suite fails"],
        )

    def test_kept_layered_file_fails_without_its_delete_tag(self):
        kept = GOOD.replace('<delete path="tests/test_validator.py"/>\n', "")

        self.assertEqual(
            grade(RULE, CASE, text=kept),
            ["2 test(s) on the shallow modules kept: test_missing_currency_is_invalid, test_negative_amount_is_invalid", "final suite fails"],
        )


HAND_LISTS = [
    "omnigent/gateway_inference.py:19 hand-lists claude-native, native-claude",
    "omnigent/gateway_inference.py:22 hand-lists codex-native, native-codex",
    "omnigent/harness_availability.py:22 hand-lists codex-native, native-codex",
]


def omnigent_sample(case, sample, diff=None):
    """Grade a sample reply with its diff, or another diff, on the pinned checkout."""
    root = RULES / RULE / "cases" / case
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    text = (root / "samples" / f"{sample}.diff").read_text() if diff is None else diff
    return grade(RULE, case, f"{sample}.md", workspace=Workspace(workspace.reference_checkout(spec)[0], text))


def omnigent_mirror():
    return workspace.has_commit(workspace.mirror_path("omnigent"), "02969a131c72d74c00c5800d8e82ae831f8ec5e5")


def new_file(path, text):
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n" + "".join(
        difflib.unified_diff([], text.splitlines(keepends=True), "/dev/null", f"b/{path}"))


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class HarnessNamesTests(unittest.TestCase):
    def test_registry_derived_spellings_pass(self):
        self.assertEqual(omnigent_sample("harness-names", "good"), [])

    def test_resolver_protocol_with_one_adapter_fails(self):
        self.assertEqual(
            omnigent_sample("harness-names", "bad"),
            [*HAND_LISTS, "omnigent/harness_names.py:HarnessNameResolver is an interface with 1 implementation"],
        )

    def test_unchanged_checkout_keeps_the_hand_lists(self):
        self.assertEqual(omnigent_sample("harness-names", "good", diff=""), HAND_LISTS)

    def test_module_that_only_forwards_calls_fails(self):
        facade = new_file("omnigent/harness_names.py", (
            '"""Harness names in one place."""\n'
            "from omnigent.gateway_inference import CLAUDE_GATEWAY_HARNESSES, CODEX_GATEWAY_HARNESSES\n"
            "from omnigent.harness_aliases import canonicalize_harness, is_native_harness\n\n"
            '__all__ = ["CLAUDE_GATEWAY_HARNESSES", "CODEX_GATEWAY_HARNESSES", "canonical", "is_native"]\n\n\n'
            "def canonical(harness):\n    return canonicalize_harness(harness)\n\n\n"
            "def is_native(harness):\n    return is_native_harness(harness)\n"
        ))

        self.assertEqual(
            omnigent_sample("harness-names", "good", diff=facade),
            [*HAND_LISTS, "omnigent/harness_names.py only passes calls through to other omnigent modules"],
        )


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class TerminalNameTests(unittest.TestCase):
    def test_registry_terminal_name_in_place_passes(self):
        self.assertEqual(omnigent_sample("terminal-name", "good"), [])

    def test_new_abc_module_for_one_function_fails(self):
        self.assertEqual(
            omnigent_sample("terminal-name", "bad"),
            [
                "the diff reaches beyond omnigent/harness_aliases.py: omnigent/harness_terminals.py",
                "omnigent/harness_terminals.py:TerminalNameSource is an interface with 1 implementation",
            ],
        )

    def test_unchanged_checkout_still_strips_by_hand(self):
        self.assertEqual(omnigent_sample("terminal-name", "good", diff=""), ["native_terminal_name still strips -native and native- by hand"])


if __name__ == "__main__":
    unittest.main()
