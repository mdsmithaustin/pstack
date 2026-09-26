The refund route lives in `OrdersApi.handle`. The tests post each spec example through it, starting with the one inside the window.

<file path="orders/http.py">
from dataclasses import dataclass, field
from datetime import timedelta

REFUND_WINDOW = timedelta(days=30)


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
            return self.request_refund(order)
        return Response(404, {"error": "not found"})

    def request_refund(self, order):
        if order.delivered_on is None:
            return Response(409, {"error": "order not delivered"})
        if self.today() - order.delivered_on > REFUND_WINDOW:
            return Response(422, {"error": "refund window closed"})
        return Response(201, {"status": "refund_requested"})
</file>

<file path="tests/test_refunds.py">
import unittest
from datetime import date

from orders.http import OrdersApi, Request
from orders.model import Order

DELIVERED_MARCH_1 = Order("A100", 4500, date(2026, 3, 1))
UNDELIVERED = Order("B200", 1200)


def post_refund(order, on):
    api = OrdersApi([order], today=lambda: on)
    return api.handle(Request("POST", f"/orders/{order.id}/refunds"))


class RefundWindowTest(unittest.TestCase):
    def test_refund_inside_the_window_is_requested(self):
        response = post_refund(DELIVERED_MARCH_1, on=date(2026, 3, 20))

        self.assertEqual(response.status, 201)
        self.assertEqual(response.body, {"status": "refund_requested"})

    def test_refund_after_the_window_is_refused(self):
        response = post_refund(DELIVERED_MARCH_1, on=date(2026, 4, 5))

        self.assertEqual(response.status, 422)
        self.assertEqual(response.body, {"error": "refund window closed"})

    def test_refund_before_delivery_is_refused(self):
        response = post_refund(UNDELIVERED, on=date(2026, 3, 20))

        self.assertEqual(response.status, 409)
        self.assertEqual(response.body, {"error": "order not delivered"})


if __name__ == "__main__":
    unittest.main()
</file>
