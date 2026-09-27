from dataclasses import dataclass, replace
from datetime import date
from enum import Enum


class SubscriptionStatus(Enum):
    ACTIVE = "active"
    CANCELED = "canceled"


@dataclass(frozen=True)
class Subscription:
    id: str
    customer_id: str
    plan: str
    status: SubscriptionStatus
    renews_on: date


def cancel_subscription(subscription: Subscription) -> Subscription:
    return replace(subscription, status=SubscriptionStatus.CANCELED)
