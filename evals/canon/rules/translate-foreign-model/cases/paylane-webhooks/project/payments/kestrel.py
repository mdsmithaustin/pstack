"""Kestrel Pay webhooks."""
from .model import PaymentStatus
from .orders import record_payment_status

_STATUS = {
    "succeeded": PaymentStatus.PAID,
    "processing": PaymentStatus.PENDING,
    "requires_payment_method": PaymentStatus.FAILED,
}


def handle(payload: dict, store) -> None:
    charge = payload["data"]["object"]
    status = _STATUS.get(charge["status"])
    if status is None:
        raise ValueError(f"unhandled Kestrel status: {charge['status']}")
    record_payment_status(store, charge["metadata"]["order_id"], status)
