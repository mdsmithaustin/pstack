from dataclasses import replace
from datetime import date, timedelta

from billing.plans import monthly_price
from billing.subscription import Subscription, SubscriptionStatus

BILLING_PERIOD = timedelta(days=30)


def due_for_renewal(subscriptions: list[Subscription], today: date) -> list[Subscription]:
    return [s for s in subscriptions if s.status is SubscriptionStatus.ACTIVE and s.renews_on <= today]


def renew(subscription: Subscription) -> tuple[Subscription, int]:
    renewed = replace(subscription, renews_on=subscription.renews_on + BILLING_PERIOD)
    return renewed, monthly_price(subscription.plan)
