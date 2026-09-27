Two callers, so one change moves both onto one `platform_http.Session` in `app/settings.py` and deletes `app/httpclient.py`. The tests swap the session's transport instead of the opener.

<commit message="Move callers to platform_http and delete httpclient">
<file path="app/settings.py">
import os

from platform_http import Session

API_URL = os.environ.get("API_URL", "http://api.internal")
SESSION = Session(API_URL)
</file>
<file path="app/billing/invoices.py">
"""Invoices."""
from app import settings


def fetch_invoice(invoice_id):
    return settings.SESSION.get(f"/invoices/{invoice_id}").json()
</file>
<file path="app/users/profile.py">
"""User profiles."""
from app import settings


def fetch_profile(user_id):
    return settings.SESSION.get(f"/users/{user_id}").json()
</file>
<file path="app/httpclient.py"></file>
<file path="tests/test_endpoints.py">
import json
import unittest

from app import settings
from app.billing.invoices import fetch_invoice
from app.users.profile import fetch_profile


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, method, url, body, headers):
        self.requests.append((method, url))
        return 200, json.dumps(self.payload).encode()


class EndpointTest(unittest.TestCase):
    def use(self, payload):
        fake = FakeTransport(payload)
        original = settings.SESSION.transport
        settings.SESSION.transport = fake
        self.addCleanup(setattr, settings.SESSION, "transport", original)
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
</file>
</commit>
