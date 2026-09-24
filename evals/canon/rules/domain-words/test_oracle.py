import unittest

from check import RULES, grade

RULE, CASE = "domain-words", "shipment-tracking"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


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
