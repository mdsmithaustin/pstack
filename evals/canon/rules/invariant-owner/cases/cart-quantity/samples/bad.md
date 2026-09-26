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
    for i, line in enumerate(order.lines):
        if line.sku == params["sku"]:
            order.lines[i].quantity = body["quantity"]
    return 200, orders.to_json(order)


ROUTES = [
    ("GET", "/cart/{order_id}", show_cart),
    ("POST", "/cart/{order_id}/lines", add_item),
    ("PATCH", "/cart/{order_id}/lines/{sku}", change_quantity),
]
</file>
