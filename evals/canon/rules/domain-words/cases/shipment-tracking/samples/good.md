CONTEXT.md calls these shipments, so the new code uses that word.

<file path="fulfillment/support.py">
from datetime import date, timedelta

from fulfillment.shipment import Shipment

OVERDUE_AFTER = timedelta(days=3)


def status_line(shipment: Shipment, today: date) -> str:
    if shipment.arrived:
        return f"Arrived on {shipment.delivered_at:%d %b}."
    if today <= shipment.promised_date:
        return f"On the way with {shipment.carrier}, expected by {shipment.promised_date:%d %b}."
    return f"On the way with {shipment.carrier}, running late."


def is_overdue(shipment: Shipment, today: date) -> bool:
    return not shipment.arrived and today - shipment.promised_date > OVERDUE_AFTER


def overdue_shipments(shipments: list[Shipment], today: date) -> list[Shipment]:
    return [shipment for shipment in shipments if is_overdue(shipment, today)]
</file>

<file path="tests/test_overdue.py">
import unittest
from datetime import date

from fulfillment.shipment import Shipment
from fulfillment.support import overdue_shipments


class OverdueShipmentsTest(unittest.TestCase):
    def test_flags_only_shipments_more_than_three_days_late(self):
        late = Shipment("s1", "o1", "DHL", date(2026, 9, 1))
        recent = Shipment("s2", "o2", "DHL", date(2026, 9, 3))
        arrived = Shipment("s3", "o3", "DHL", date(2026, 9, 1), delivered_at=date(2026, 9, 5))
        self.assertEqual(overdue_shipments([late, recent, arrived], date(2026, 9, 5)), [late])
</file>
