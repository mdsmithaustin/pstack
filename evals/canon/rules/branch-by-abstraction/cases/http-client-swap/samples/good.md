Nine call sites in eight modules call `httpclient` directly, so one reviewable PR a day means a seam first. `app/api.py` goes in front of `httpclient`, callers move to it a package at a time, then it switches to `platform_http`. The last PR deletes `httpclient` and `app/api.py`, since only one implementation remains.

<plan>
1. Add `app/api.py` with `get_json` and `post_json` that delegate to `httpclient`. Move the billing callers to it.
2. Move the catalog and orders callers to `app.api`.
3. Move the users callers to `app.api`. No module outside `app/api.py` imports `httpclient`.
4. Back `app/api.py` with `platform_http.Session`. Tests swap in a fake transport.
5. Delete `app/httpclient.py`. Point every caller at `platform_http` directly and delete `app/api.py`, since one implementation remains.
</plan>

<commit message="Add app.api in front of httpclient">
<file path="app/api.py">
"""The one place callers reach the HTTP API while it moves to platform_http."""
from app import httpclient


def get_json(path):
    return httpclient.get_json(path)


def post_json(path, body):
    return httpclient.post_json(path, body)
</file>
</commit>

<commit message="Move billing callers to app.api">
<file path="app/billing/invoices.py">
"""Invoices."""
from app import api


def fetch_invoice(invoice_id):
    return api.get_json(f"/invoices/{invoice_id}")
</file>
<file path="app/billing/refunds.py">
"""Refunds."""
from app import api


def request_refund(invoice_id, cents):
    return api.post_json("/refunds", {"invoice": invoice_id, "cents": cents})
</file>
</commit>
