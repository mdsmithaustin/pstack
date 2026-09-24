from dataclasses import dataclass, replace
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


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
