import importlib.util
import json
import unittest

from check import RULES, grade
from shared import Workspace

RULE, CASE = "route-domain-modeling", "order-line-items"
_spec = importlib.util.spec_from_file_location("canon_workspace_route_domain_modeling", RULES.parent / "workspace.py")
workspace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workspace)
HERMES = "130b8f2c5dbca93a81aa396dd2ba44420d78f6f0"


def hermes_available():
    return workspace.has_commit(workspace.mirror_path("hermes"), HERMES)


def sample_workspace(case, sample, diff=None):
    """The case's pinned checkout with its overlay, and the sample's diff."""
    root = RULES / RULE / "cases" / case
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    checkout, _ = workspace.reference_checkout(spec)
    return Workspace(checkout, diff if diff is not None else (root / "samples" / sample).read_text(encoding="utf-8"))


class OrderLineItemsTests(unittest.TestCase):
    def test_amendment_named_from_the_glossary_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_line_item_cancellation_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "no new function or class carries the glossary's Amendment; new names are ['cancel_line_items']",
                "cancel_line_items uses a term CONTEXT.md lists under Avoid",
            ],
        )

    def test_avoided_file_name_fails_even_with_an_amendment_function(self):
        good = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text(encoding="utf-8")
        renamed = good.replace("orders/amend.py", "orders/partial_cancel.py").replace("from orders.amend", "from orders.partial_cancel")

        self.assertEqual(grade(RULE, CASE, text=renamed), ["orders/partial_cancel.py uses a term CONTEXT.md lists under Avoid"])


@unittest.skipUnless(hermes_available(), f"needs hermes {HERMES} in the mirror; run workspace.py fetch hermes")
class SessionTreeTests(unittest.TestCase):
    CASE = "session-tree"

    def test_recorded_session_tree_passes(self):
        self.assertEqual(grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, "good.diff")), [])

    def test_fork_and_chain_names_without_a_term_fail(self):
        self.assertEqual(
            grade(RULE, self.CASE, "bad.md", workspace=sample_workspace(self.CASE, "bad.diff")),
            [
                "CONTEXT.md gains no term",
                "new name chain uses the word chain",
                "new name fork uses the word fork",
                "new name fork_children uses the word fork",
                "new name forks uses the word forks",
            ],
        )

    def test_recorded_term_that_names_no_code_fails(self):
        good = (RULES / RULE / "cases" / self.CASE / "samples" / "good.diff").read_text(encoding="utf-8")
        diff = good.replace("+**Session tree**:", "+**Descendants**:")
        self.assertEqual(
            grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, None, diff)),
            ["no new name carries a term CONTEXT.md gains; new terms are ['descendants']"],
        )


@unittest.skipUnless(hermes_available(), f"needs hermes {HERMES} in the mirror; run workspace.py fetch hermes")
class CronPausedReasonTests(unittest.TestCase):
    CASE = "cron-paused-reason"

    def test_listing_change_alone_passes(self):
        self.assertEqual(grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, "good.diff")), [])

    def test_new_glossary_fails(self):
        self.assertEqual(
            grade(RULE, self.CASE, "bad.md", workspace=sample_workspace(self.CASE, "bad.diff")),
            ["the diff writes CONTEXT.md"],
        )

    def test_empty_diff_fails(self):
        self.assertEqual(
            grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, None, "")),
            ["hermes_cli/cron.py gains no use of paused_reason"],
        )


if __name__ == "__main__":
    unittest.main()
