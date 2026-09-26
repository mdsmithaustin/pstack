from billing.store import SubscriptionStore
from billing.subscription import cancel_subscription


def cancel(store: SubscriptionStore, subscription_id: str) -> dict:
    subscription = cancel_subscription(store.get(subscription_id))
    store.save(subscription)
    return {"id": subscription.id, "status": subscription.status.value}
