import importlib.util
import json
import unittest

from check import RULES, grade
from shared import Workspace

RULE, CASE = "domain-words", "shipment-tracking"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"
_spec = importlib.util.spec_from_file_location("canon_workspace_domain_words", RULES.parent / "workspace.py")
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


class ShipmentTrackingTests(unittest.TestCase):
    def test_glossary_words_pass(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_avoided_word_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "new name DELIVERY_GRACE uses the word delivery",
                "new name LateDeliveriesTest uses the word delivery",
                "new name deliveries uses the word delivery",
                "new name late_deliveries uses the word delivery",
                "new name test_deliveries uses the word delivery",
                "new name test_flags_late_delivery uses the word delivery",
                "no new name uses the word shipment",
            ],
        )

    def test_existing_delivered_at_field_is_not_new(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "return not shipment.arrived and", "return shipment.delivered_at is None and"
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_one_avoided_local_name_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "return [shipment for shipment in shipments if is_overdue(shipment, today)]",
            "late_delivery = [shipment for shipment in shipments if is_overdue(shipment, today)]\n    return late_delivery",
        )
        self.assertEqual(grade(RULE, CASE, text=answer), ["new name late_delivery uses the word delivery"])


@unittest.skipUnless(hermes_available(), f"needs hermes {HERMES} in the mirror; run workspace.py fetch hermes")
class SessionLineageUsageTests(unittest.TestCase):
    CASE = "session-lineage-usage"

    def test_lineage_usage_passes(self):
        self.assertEqual(grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, "good.diff")), [])

    def test_chain_and_conversation_names_fail(self):
        self.assertEqual(
            grade(RULE, self.CASE, "bad.md", workspace=sample_workspace(self.CASE, "bad.diff")),
            [
                "new name _print_chain_totals uses the word chain",
                "new name chain uses the word chain",
                "new name conversation_usage uses the word conversation",
                "no new name uses the word lineage",
            ],
        )

    def test_chain_local_in_a_new_method_fails_beside_an_old_one(self):
        good = (RULES / RULE / "cases" / self.CASE / "samples" / "good.diff").read_text(encoding="utf-8")
        diff = good.replace("+        lineage = self.get_compression_lineage", "+        chain = lineage = self.get_compression_lineage")
        self.assertEqual(
            grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, None, diff)),
            ["new name chain uses the word chain"],
        )


@unittest.skipUnless(hermes_available(), f"needs hermes {HERMES} in the mirror; run workspace.py fetch hermes")
class SessionStatsJsonTests(unittest.TestCase):
    CASE = "session-stats-json"

    def test_json_flag_passes(self):
        self.assertEqual(grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, "good.diff")), [])

    def test_renamed_handler_fails(self):
        self.assertEqual(
            grade(RULE, self.CASE, "bad.md", workspace=sample_workspace(self.CASE, "bad.diff")),
            ["hermes_cli/sessions_cmd.py no longer defines _cmd_stats"],
        )

    def test_empty_diff_fails(self):
        self.assertEqual(
            grade(RULE, self.CASE, "good.md", workspace=sample_workspace(self.CASE, None, "")),
            ["the stats parser takes no --json flag", "no added line in hermes_cli/sessions_cmd*.py reads args.json"],
        )
