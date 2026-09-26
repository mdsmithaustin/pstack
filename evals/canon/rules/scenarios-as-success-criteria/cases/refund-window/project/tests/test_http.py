import unittest
from datetime import date

from orders.http import OrdersApi, Request
from orders.model import Order


class GetOrderTest(unittest.TestCase):
    def test_delivered_order_shows_its_delivery_date(self):
        api = OrdersApi([Order("A100", 4500, date(2026, 3, 1))], today=lambda: date(2026, 3, 2))

        response = api.handle(Request("GET", "/orders/A100"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, {"id": "A100", "total_cents": 4500, "delivered_on": "2026-03-01"})

    def test_unknown_order_is_not_found(self):
        api = OrdersApi([], today=lambda: date(2026, 3, 2))

        response = api.handle(Request("GET", "/orders/Z999"))

        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
