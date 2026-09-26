"""Refunds."""
from app import httpclient


def request_refund(invoice_id, cents):
    return httpclient.post_json("/refunds", {"invoice": invoice_id, "cents": cents})
