<file path="billing/membership.py">
from dataclasses import dataclass
from datetime import date, timedelta

from billing.subscription import Subscription

MAX_MEMBERSHIP_PAUSE = timedelta(days=60)


@dataclass(frozen=True)
class MembershipPause:
    membership_id: str
    starts_on: date
    ends_on: date


def pause_membership(membership: Subscription, today: date, until: date) -> MembershipPause:
    if until - today > MAX_MEMBERSHIP_PAUSE:
        raise ValueError("a pause lasts at most 60 days")
    return MembershipPause(membership.id, today, until)
</file>
