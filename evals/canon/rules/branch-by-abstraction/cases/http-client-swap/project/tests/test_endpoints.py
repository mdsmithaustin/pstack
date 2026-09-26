import io
import json
import unittest

from app import httpclient
from app.billing.refunds import request_refund
from app.catalog.products import search_products
from app.orders.status import order_status
from app.users.profile import fetch_profile


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append((request.get_method(), request.full_url, request.data))
        return io.BytesIO(json.dumps(self.payload).encode())


class EndpointTest(unittest.TestCase):
    def use(self, payload):
        fake = FakeOpener(payload)
        original = httpclient.OPENER
        httpclient.OPENER = fake
        self.addCleanup(setattr, httpclient, "OPENER", original)
        return fake

    def test_profile_is_fetched_by_user_id(self):
        fake = self.use({"id": "u1", "name": "Ada"})

        self.assertEqual(fetch_profile("u1"), {"id": "u1", "name": "Ada"})
        self.assertEqual(fake.requests, [("GET", "http://api.internal/users/u1", None)])

    def test_order_status_reads_the_status_field(self):
        self.use({"id": "o9", "status": "shipped"})

        self.assertEqual(order_status("o9"), "shipped")

    def test_search_returns_items(self):
        self.use({"items": [{"sku": "A1"}]})

        self.assertEqual(search_products("lamp"), [{"sku": "A1"}])

    def test_refund_posts_invoice_and_amount(self):
        fake = self.use({"ok": True})

        request_refund("inv-3", 1200)
        self.assertEqual(fake.requests, [("POST", "http://api.internal/refunds", b'{"invoice": "inv-3", "cents": 1200}')])


if __name__ == "__main__":
    unittest.main()
