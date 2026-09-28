<file path="fulfillment/deliveries.py">
from datetime import date, timedelta

from fulfillment.store import ShipmentStore

DELIVERY_GRACE = timedelta(days=3)


def late_deliveries(store: ShipmentStore, today: date):
    return [s for s in store.all() if s.delivered_at is None and today - s.promised_date > DELIVERY_GRACE]
</file>

<file path="tests/test_deliveries.py">
import unittest
from datetime import date

from fulfillment.deliveries import late_deliveries
from fulfillment.shipment import Shipment
from fulfillment.store import ShipmentStore


class LateDeliveriesTest(unittest.TestCase):
    def test_flags_late_delivery(self):
        late = Shipment("s1", "o1", "DHL", date(2026, 9, 1))
        self.assertEqual(late_deliveries(ShipmentStore([late]), date(2026, 9, 5)), [late])
</file>
