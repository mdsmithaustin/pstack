"""Invoices."""
from app import httpclient


def fetch_invoice(invoice_id):
    return httpclient.get_json(f"/invoices/{invoice_id}")
