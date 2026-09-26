import unittest

from payments.model import Order, PaymentStatus
from payments.webhooks import dispatch


class MemoryStore:
    def __init__(self, *orders):
        self.orders = {order.id: order for order in orders}

    def get(self, order_id):
        return self.orders[order_id]

    def save(self, order):
        self.orders[order.id] = order


class KestrelWebhookTest(unittest.TestCase):
    def test_succeeded_charge_marks_order_paid(self):
        store = MemoryStore(Order("ord_7", 1200))

        dispatch("kestrel", {"data": {"object": {"status": "succeeded", "metadata": {"order_id": "ord_7"}}}}, store)

        self.assertEqual(store.get("ord_7").payment, PaymentStatus.PAID)


if __name__ == "__main__":
    unittest.main()
