I put the window rule in its own module and wired it into the API.

<file path="orders/refunds.py">
from datetime import timedelta

REFUND_WINDOW = timedelta(days=30)


def is_within_window(delivered_on, today):
    return delivered_on is not None and today - delivered_on <= REFUND_WINDOW
</file>

<file path="orders/http.py">
from dataclasses import dataclass, field

from orders.refunds import is_within_window


@dataclass
class Request:
    method: str
    path: str
    body: dict = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: dict


class OrdersApi:
    def __init__(self, orders, today):
        self.orders = {order.id: order for order in orders}
        self.today = today

    def handle(self, request):
        parts = request.path.strip("/").split("/")
        if parts[0] != "orders" or len(parts) < 2:
            return Response(404, {"error": "not found"})
        order = self.orders.get(parts[1])
        if order is None:
            return Response(404, {"error": "order not found"})
        if request.method == "GET" and len(parts) == 2:
            delivered = order.delivered_on.isoformat() if order.delivered_on else None
            return Response(200, {"id": order.id, "total_cents": order.total_cents, "delivered_on": delivered})
        if request.method == "POST" and parts[2:] == ["refunds"]:
            if order.delivered_on is None:
                return Response(409, {"error": "order not delivered"})
            if not is_within_window(order.delivered_on, self.today()):
                return Response(422, {"error": "refund window closed"})
            return Response(201, {"status": "refund_requested"})
        return Response(404, {"error": "not found"})
</file>

<file path="tests/test_refunds.py">
import unittest
from datetime import date

from orders.http import OrdersApi, Request
from orders.model import Order
from orders.refunds import is_within_window


class WindowTest(unittest.TestCase):
    def test_day_19_is_within_window(self):
        self.assertTrue(is_within_window(date(2026, 3, 1), date(2026, 3, 20)))

    def test_day_35_is_outside_window(self):
        self.assertFalse(is_within_window(date(2026, 3, 1), date(2026, 4, 5)))

    def test_undelivered_is_outside_window(self):
        self.assertFalse(is_within_window(None, date(2026, 3, 20)))


class RefundEndpointTest(unittest.TestCase):
    def test_post_refund_returns_201(self):
        api = OrdersApi([Order("A100", 4500, date(2026, 3, 1))], today=lambda: date(2026, 3, 20))

        response = api.handle(Request("POST", "/orders/A100/refunds"))

        self.assertEqual(response.status, 201)
        self.assertEqual(response.body, {"status": "refund_requested"})


if __name__ == "__main__":
    unittest.main()
</file>
