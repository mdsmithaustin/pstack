An `app/api.py` interface goes in front of `httpclient` first, so the swap to `platform_http` can follow later behind it.

<commit message="Add app.api in front of httpclient and move callers">
<file path="app/api.py">
"""The one place callers reach the HTTP API."""
from app import httpclient


def get_json(path):
    return httpclient.get_json(path)
</file>
<file path="app/billing/invoices.py">
"""Invoices."""
from app import api


def fetch_invoice(invoice_id):
    return api.get_json(f"/invoices/{invoice_id}")
</file>
<file path="app/users/profile.py">
"""User profiles."""
from app import api


def fetch_profile(user_id):
    return api.get_json(f"/users/{user_id}")
</file>
</commit>
