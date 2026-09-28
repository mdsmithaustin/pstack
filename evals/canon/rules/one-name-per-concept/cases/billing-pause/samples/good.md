The code calls memberships subscriptions, so I added the pause to `Subscription` and kept that word.

<file path="billing/subscription.py">
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import Enum

MAX_PAUSE = timedelta(days=60)


class SubscriptionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELED = "canceled"


@dataclass(frozen=True)
class Subscription:
    id: str
    customer_id: str
    plan: str
    status: SubscriptionStatus
    renews_on: date
    paused_until: date | None = None


def cancel_subscription(subscription: Subscription) -> Subscription:
    return replace(subscription, status=SubscriptionStatus.CANCELED)


def pause_subscription(subscription: Subscription, today: date, until: date) -> Subscription:
    if until - today > MAX_PAUSE:
        raise ValueError("a pause lasts at most 60 days")
    shift = until - today
    return replace(subscription, status=SubscriptionStatus.PAUSED, paused_until=until, renews_on=subscription.renews_on + shift)
</file>

<file path="billing/api.py">
from datetime import date

from billing.store import SubscriptionStore
from billing.subscription import cancel_subscription, pause_subscription


def cancel(store: SubscriptionStore, subscription_id: str) -> dict:
    subscription = cancel_subscription(store.get(subscription_id))
    store.save(subscription)
    return {"id": subscription.id, "status": subscription.status.value}


def pause(store: SubscriptionStore, subscription_id: str, today: date, until: date) -> dict:
    subscription = pause_subscription(store.get(subscription_id), today, until)
    store.save(subscription)
    return {"id": subscription.id, "status": subscription.status.value, "paused_until": until.isoformat()}
</file>
