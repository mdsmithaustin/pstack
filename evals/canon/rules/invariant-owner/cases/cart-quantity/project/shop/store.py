from shop.order import Order


class OrderStore:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def get(self, order_id: str) -> Order:
        return self._orders.setdefault(order_id, Order(order_id))
