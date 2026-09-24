import json
import sys
import unittest

from check import RULES, grade
from shared import Workspace

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE = "converge-within-context"
ACCOUNTS = RULES / RULE / "cases" / "account-types" / "samples"


class AccountTypesTests(unittest.TestCase):
    def test_separate_types_with_shared_id_pass(self):
        self.assertEqual(grade(RULE, "account-types", "good.md"), [])

    def test_merged_optional_fields_fail(self):
        self.assertEqual(
            grade(RULE, "account-types", "bad.md"),
            [
                "accounts.py:Account mixes billing fields with sign-in fields",
                "no type keeps the billing account's fields",
                "no type keeps the sign-in account's fields",
            ],
        )

    def test_unchanged_project_passes(self):
        self.assertEqual(grade(RULE, "account-types", text="These are different concepts; I left them apart."), [])


class InvoiceCustomersTests(unittest.TestCase):
    def test_one_merged_customer_passes(self):
        self.assertEqual(grade(RULE, "invoice-customers", "good.md"), [])

    def test_kept_duplicate_fails(self):
        self.assertEqual(
            grade(RULE, "invoice-customers", "bad.md"),
            ["2 types hold a customer's id, name, and email: invoicing/mailer.py:InvoiceCustomer, invoicing/pdf.py:Customer"],
        )


def omnigent_sample(case, sample, diff=None):
    """Grade a sample reply with its diff, or another diff, on the pinned checkout."""
    root = RULES / RULE / "cases" / case
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    text = (root / "samples" / f"{sample}.diff").read_text() if diff is None else diff
    return grade(RULE, case, f"{sample}.md", workspace=Workspace(workspace.reference_checkout(spec)[0], text))


def omnigent_mirror():
    return workspace.has_commit(workspace.mirror_path("omnigent"), "02969a131c72d74c00c5800d8e82ae831f8ec5e5")


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class HarnessFamiliesTests(unittest.TestCase):
    def test_three_lookups_under_three_names_pass(self):
        self.assertEqual(omnigent_sample("harness-families", "good"), [])

    def test_one_table_for_every_family_fails(self):
        self.assertEqual(
            omnigent_sample("harness-families", "bad"),
            [
                "omnigent/harness_families.py:_HARNESS_FAMILY mixes provider, routing, skill-vendor family values",
                "omnigent/harness_families.py:harness_family mixes provider, routing, skill-vendor family values",
                "omnigent/harness_families.py:HarnessFamily holds fields from more than one family lookup: provider, routing",
            ],
        )

    def test_pushing_back_without_an_edit_passes(self):
        self.assertEqual(omnigent_sample("harness-families", "good", diff=""), [])


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class SubagentRoutingWrapperTests(unittest.TestCase):
    def test_folded_wrapper_passes(self):
        self.assertEqual(omnigent_sample("subagent-routing-wrapper", "good"), [])

    def test_kept_wrapper_fails(self):
        self.assertEqual(omnigent_sample("subagent-routing-wrapper", "bad"), ["omnigent/runner/subagent_routing.py still defines _harness_family"])

    def test_one_table_for_every_family_fails_here_too(self):
        merged = (RULES / RULE / "cases" / "harness-families" / "samples" / "bad.diff").read_text()

        self.assertEqual(
            omnigent_sample("subagent-routing-wrapper", "good", diff=merged),
            [
                "omnigent/harness_families.py:_HARNESS_FAMILY mixes provider, routing, skill-vendor family values",
                "omnigent/harness_families.py:harness_family mixes provider, routing, skill-vendor family values",
                "omnigent/harness_families.py:HarnessFamily holds fields from more than one family lookup: provider, routing",
                "omnigent/runner/subagent_routing.py still defines _harness_family",
            ],
        )
