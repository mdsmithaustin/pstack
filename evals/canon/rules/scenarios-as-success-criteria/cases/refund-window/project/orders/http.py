from dataclasses import dataclass, field


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
        return Response(404, {"error": "not found"})
