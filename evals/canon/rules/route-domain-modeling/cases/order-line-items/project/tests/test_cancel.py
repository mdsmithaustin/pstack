import unittest

from orders.cancel import OrderLocked, cancel_order
from orders.models import LineItem, Order


def placed_order():
    return Order("o-1", "placed", [LineItem("mug", 2, 1200), LineItem("tee", 1, 2500)])


class CancelOrderTests(unittest.TestCase):
    def test_cancelling_refunds_the_whole_order(self):
        order = cancel_order(placed_order())

        self.assertEqual((order.status, order.refunded_cents), ("cancelled", 4900))

    def test_shipped_order_cannot_be_cancelled(self):
        order = placed_order()
        order.status = "shipped"

        with self.assertRaises(OrderLocked):
            cancel_order(order)


if __name__ == "__main__":
    unittest.main()
