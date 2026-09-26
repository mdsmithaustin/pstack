<file path="payments/model.py">
from dataclasses import dataclass, replace
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    AUTH_OK = "AUTH_OK"
    CAPTURED = "CAPTURED"
    DECLINED = "DECLINED"
    REFUNDED_PARTIAL = "REFUNDED_PARTIAL"


@dataclass(frozen=True)
class Order:
    id: str
    total_cents: int
    payment: PaymentStatus = PaymentStatus.PENDING
    cancelled_reason: str | None = None

    def with_payment(self, status: PaymentStatus) -> "Order":
        return replace(self, payment=status)

    def mark_paid(self) -> "Order":
        return replace(self, payment=PaymentStatus.PAID)

    def cancel(self, reason: str) -> "Order":
        return replace(self, payment=PaymentStatus.FAILED, cancelled_reason=reason)
</file>

<file path="payments/paylane.py">
from .model import PaymentStatus
from .orders import record_payment_status


def handle(payload: dict, store) -> None:
    record_payment_status(store, payload["merchant_ref"], PaymentStatus(payload["state"]))
</file>

<file path="payments/orders.py">
from .model import Order, PaymentStatus


def record_payment_status(store, order_id: str, status: PaymentStatus) -> Order:
    order = store.get(order_id)
    if status in (PaymentStatus.PAID, PaymentStatus.CAPTURED):
        updated = order.mark_paid()
    elif status in (PaymentStatus.FAILED, PaymentStatus.DECLINED):
        updated = order.cancel("payment failed")
    else:
        updated = order.with_payment(status)
    store.save(updated)
    return updated
</file>
