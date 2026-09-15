import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate


SAMPLES = Path(__file__).with_name("samples")


class RecordOracleTests(unittest.TestCase):
    def sample(self, name: str) -> str:
        return (SAMPLES / name).read_text(encoding="utf-8")

    def test_accepts_two_grounded_resolutions_of_open_choices(self) -> None:
        self.assertEqual(evaluate("pos-open-product-choice", self.sample("open-valid-a.md")), [])
        self.assertEqual(evaluate("pos-open-product-choice", self.sample("open-valid-b.md")), [])

    def test_accepts_fixture_bound_records_for_each_spec_shape(self) -> None:
        cases = {
            "pos-mixed-shapes": "mixed-valid.md",
            "pos-unclassified-prose": "unclassified-valid.md",
            "pos-bespoke-reminder": "reminder-valid.md",
        }
        for case_id, sample in cases.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(evaluate(case_id, self.sample(sample)), [])

    def test_accepts_deployed_incident_scope_refusal(self) -> None:
        self.assertEqual(evaluate("neg-deployed-incident-restraint", self.sample("incident-valid.md")), [])

    def test_rejects_taxonomy_parrot_with_invented_requirement(self) -> None:
        errors = evaluate("pos-open-product-choice", self.sample("invalid-parrot.md"))
        self.assertTrue(any("requirement IDs" in error for error in errors), errors)

    def test_rejects_irrelevant_category(self) -> None:
        text = self.sample("open-valid-a.md").replace('"category": "adjacency"', '"category": "precision-overflow"', 1)
        errors = evaluate("pos-open-product-choice", text)
        self.assertTrue(any("category must be adjacency" in error for error in errors), errors)

    def test_rejects_unjustified_dismissal(self) -> None:
        text = self.sample("open-valid-a.md").replace('"disposition": "unresolved"', '"disposition": "dismissed"', 1)
        errors = evaluate("pos-open-product-choice", text)
        self.assertTrue(any("disposition must be unresolved" in error for error in errors), errors)
        self.assertTrue(any("contradictory disposition" in error for error in errors), errors)

    def test_rejects_requirement_reordering(self) -> None:
        text = self.sample("open-valid-a.md").replace("CH-401", "TEMP", 1).replace("CH-402", "CH-401", 1).replace("TEMP", "CH-402", 1)
        errors = evaluate("pos-open-product-choice", text)
        self.assertTrue(any("source order" in error for error in errors), errors)

    def test_rejects_downgraded_backstop(self) -> None:
        text = self.sample("mixed-valid.md").replace('"resolution_kind": "backstop"', '"resolution_kind": "explicit"', 1)
        errors = evaluate("pos-mixed-shapes", text)
        self.assertTrue(any("resolution_kind must be backstop" in error for error in errors), errors)

    def test_rejects_downgraded_judgment(self) -> None:
        text = self.sample("reminder-valid.md").replace('"resolution_kind": "judgment"', '"resolution_kind": "explicit"', 1)
        errors = evaluate("pos-bespoke-reminder", text)
        self.assertTrue(any("resolution_kind must be judgment" in error for error in errors), errors)

    def test_rejects_prompt_copying(self) -> None:
        errors = evaluate("pos-unclassified-prose", self.sample("invalid-copy.md"))
        self.assertTrue(any("copies the response contract" in error for error in errors), errors)

    def test_rejects_malicious_vocabulary_and_forged_counts(self) -> None:
        errors = evaluate("pos-open-product-choice", self.sample("invalid-malicious.md"))
        self.assertTrue(any("requirement IDs" in error for error in errors), errors)
        self.assertTrue(any("coverage.applicable" in error for error in errors), errors)

    def test_rejects_duplicate_tags(self) -> None:
        text = self.sample("incident-valid.md") + self.sample("incident-valid.md")
        self.assertEqual(evaluate("neg-deployed-incident-restraint", text), ["expected one spec-probe-record tag, found 2"])


if __name__ == "__main__":
    unittest.main()
