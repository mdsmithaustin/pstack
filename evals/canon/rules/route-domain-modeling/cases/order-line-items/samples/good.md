CONTEXT.md already names this. Dropping line items from an unshipped order is an Amendment, and removing every line item is a Cancellation. The new module follows those terms.

<file path="orders/amend.py">
from orders.cancel import OrderLocked, cancel_order


def amend_order(order, skus):
    if order.status != "placed":
        raise OrderLocked(f"order {order.id} is {order.status}")
    removed = [item for item in order.line_items if item.sku in skus]
    if len(removed) == len(order.line_items):
        return cancel_order(order)
    order.line_items = [item for item in order.line_items if item.sku not in skus]
    order.refunded_cents += sum(item.total_cents for item in removed)
    return order
</file>

<file path="tests/test_amend.py">
import unittest

from orders.amend import amend_order
from orders.cancel import OrderLocked
from orders.models import LineItem, Order


def placed_order():
    return Order("o-1", "placed", [LineItem("mug", 2, 1200), LineItem("tee", 1, 2500)])


class AmendOrderTests(unittest.TestCase):
    def test_amendment_refunds_only_the_removed_items(self):
        order = amend_order(placed_order(), {"tee"})

        self.assertEqual((order.status, [item.sku for item in order.line_items], order.refunded_cents), ("placed", ["mug"], 2500))

    def test_removing_every_item_is_a_cancellation(self):
        order = amend_order(placed_order(), {"mug", "tee"})

        self.assertEqual((order.status, order.refunded_cents), ("cancelled", 4900))

    def test_shipped_order_cannot_be_amended(self):
        order = placed_order()
        order.status = "shipped"

        with self.assertRaises(OrderLocked):
            amend_order(order, {"tee"})


if __name__ == "__main__":
    unittest.main()
</file>
