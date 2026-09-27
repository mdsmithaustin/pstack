Paylane's states map onto the statuses we already have. A partial refund is something the order code cannot act on yet, so the handler rejects it loudly.

<file path="payments/paylane.py">
"""Paylane webhooks."""
from .model import PaymentStatus
from .orders import record_payment_status

_STATUS = {
    "AUTH_OK": PaymentStatus.PENDING,
    "CAPTURED": PaymentStatus.PAID,
    "DECLINED": PaymentStatus.FAILED,
}


def handle(payload: dict, store) -> None:
    status = _STATUS.get(payload["state"])
    if status is None:
        raise ValueError(f"unhandled Paylane state: {payload['state']}")
    record_payment_status(store, payload["merchant_ref"], status)
</file>

<file path="payments/webhooks.py">
from . import kestrel, paylane

HANDLERS = {
    "kestrel": kestrel.handle,
    "paylane": paylane.handle,
}


def dispatch(provider: str, payload: dict, store) -> None:
    try:
        handler = HANDLERS[provider]
    except KeyError:
        raise ValueError(f"unknown payment provider: {provider}") from None
    handler(payload, store)
</file>

<file path="tests/test_paylane.py">
import unittest

from payments.model import Order, PaymentStatus
from payments.webhooks import dispatch
from tests.test_kestrel import MemoryStore


class PaylaneWebhookTest(unittest.TestCase):
    def test_captured_payment_marks_order_paid(self):
        store = MemoryStore(Order("ord_1042", 4599))

        dispatch("paylane", {"merchant_ref": "ord_1042", "state": "CAPTURED"}, store)

        self.assertEqual(store.get("ord_1042").payment, PaymentStatus.PAID)
</file>
