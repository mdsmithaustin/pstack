Added line-item cancellation next to the whole-order cancel.

<file path="orders/cancel.py">
class OrderLocked(Exception):
    pass


def cancel_order(order):
    if order.status == "shipped":
        raise OrderLocked(f"order {order.id} has shipped")
    if order.status == "cancelled":
        return order
    order.refunded_cents += order.total_cents
    order.status = "cancelled"
    return order


def cancel_line_items(order, skus):
    if order.status != "placed":
        raise OrderLocked(f"order {order.id} is {order.status}")
    removed = [item for item in order.line_items if item.sku in skus]
    order.line_items = [item for item in order.line_items if item.sku not in skus]
    order.refunded_cents += sum(item.total_cents for item in removed)
    return order
</file>

<file path="tests/test_cancel_line_items.py">
import unittest

from orders.cancel import cancel_line_items
from orders.models import LineItem, Order


class CancelLineItemsTests(unittest.TestCase):
    def test_refunds_only_the_cancelled_items(self):
        order = Order("o-1", "placed", [LineItem("mug", 2, 1200), LineItem("tee", 1, 2500)])

        order = cancel_line_items(order, {"tee"})

        self.assertEqual(([item.sku for item in order.line_items], order.refunded_cents), (["mug"], 2500))


if __name__ == "__main__":
    unittest.main()
</file>
