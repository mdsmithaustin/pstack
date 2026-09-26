import unittest
from datetime import date

from billing.renewals import due_for_renewal, renew
from billing.subscription import Subscription, SubscriptionStatus


class RenewalTest(unittest.TestCase):
    def test_active_subscription_past_its_date_is_due(self):
        subscription = Subscription("s1", "c1", "plus", SubscriptionStatus.ACTIVE, date(2026, 9, 1))
        self.assertEqual(due_for_renewal([subscription], date(2026, 9, 2)), [subscription])

    def test_renew_charges_the_plan_price(self):
        subscription = Subscription("s1", "c1", "plus", SubscriptionStatus.ACTIVE, date(2026, 9, 1))
        renewed, charge = renew(subscription)
        self.assertEqual((renewed.renews_on, charge), (date(2026, 10, 1), 1900))
