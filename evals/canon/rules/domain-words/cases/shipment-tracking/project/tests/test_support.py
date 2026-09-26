import unittest
from datetime import date

from fulfillment.shipment import Shipment
from fulfillment.support import status_line


class StatusLineTest(unittest.TestCase):
    def test_arrived(self):
        shipment = Shipment("s1", "o1", "DHL", date(2026, 9, 10), delivered_at=date(2026, 9, 9))
        self.assertEqual(status_line(shipment, date(2026, 9, 12)), "Arrived on 09 Sep.")

    def test_on_the_way(self):
        shipment = Shipment("s2", "o2", "UPS", date(2026, 9, 20))
        self.assertEqual(status_line(shipment, date(2026, 9, 18)), "On the way with UPS, expected by 20 Sep.")
