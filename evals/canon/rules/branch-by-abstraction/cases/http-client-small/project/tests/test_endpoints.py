import io
import json
import unittest

from app import httpclient
from app.billing.invoices import fetch_invoice
from app.users.profile import fetch_profile


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append((request.get_method(), request.full_url))
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
        self.assertEqual(fake.requests, [("GET", "http://api.internal/users/u1")])

    def test_invoice_is_fetched_by_id(self):
        fake = self.use({"id": "inv-3", "cents": 1200})

        self.assertEqual(fetch_invoice("inv-3"), {"id": "inv-3", "cents": 1200})
        self.assertEqual(fake.requests, [("GET", "http://api.internal/invoices/inv-3")])


if __name__ == "__main__":
    unittest.main()
