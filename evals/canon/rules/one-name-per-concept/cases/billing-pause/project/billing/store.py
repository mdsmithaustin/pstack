from billing.subscription import Subscription


class SubscriptionStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Subscription] = {}

    def get(self, subscription_id: str) -> Subscription:
        return self._by_id[subscription_id]

    def save(self, subscription: Subscription) -> None:
        self._by_id[subscription.id] = subscription

    def all(self) -> list[Subscription]:
        return list(self._by_id.values())
