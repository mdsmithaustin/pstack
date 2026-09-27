The order owns its total, so the quantity change goes through a new `change_quantity` in `shop/order.py`.

<file path="shop/order.py">
from dataclasses import dataclass, field


@dataclass
class Line:
    sku: str
    unit_price_cents: int
    quantity: int


@dataclass
class Order:
    id: str
    lines: list[Line] = field(default_factory=list)
    total_cents: int = 0


def add_line(order: Order, sku: str, unit_price_cents: int, quantity: int) -> None:
    for line in order.lines:
        if line.sku == sku:
            line.quantity += quantity
            break
    else:
        order.lines.append(Line(sku, unit_price_cents, quantity))
    order.total_cents += unit_price_cents * quantity


def to_json(order: Order) -> dict:
    return {
        "id": order.id,
        "lines": [{"sku": line.sku, "unit_price_cents": line.unit_price_cents, "quantity": line.quantity} for line in order.lines],
        "total_cents": order.total_cents,
    }


def change_quantity(order: Order, sku: str, quantity: int) -> None:
    for line in order.lines:
        if line.sku == sku:
            order.total_cents += line.unit_price_cents * (quantity - line.quantity)
            line.quantity = quantity
            return
    raise KeyError(sku)
</file>

<file path="shop/routes/cart.py">
from shop import order as orders


def show_cart(store, params, body):
    return 200, orders.to_json(store.get(params["order_id"]))


def add_item(store, params, body):
    order = store.get(params["order_id"])
    orders.add_line(order, body["sku"], body["unit_price_cents"], body["quantity"])
    return 201, orders.to_json(order)


def change_quantity(store, params, body):
    order = store.get(params["order_id"])
    orders.change_quantity(order, params["sku"], body["quantity"])
    return 200, orders.to_json(order)


ROUTES = [
    ("GET", "/cart/{order_id}", show_cart),
    ("POST", "/cart/{order_id}/lines", add_item),
    ("PATCH", "/cart/{order_id}/lines/{sku}", change_quantity),
]
</file>
