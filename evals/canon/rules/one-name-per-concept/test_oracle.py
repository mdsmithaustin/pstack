import unittest

from check import RULES, grade

RULE, CASE = "one-name-per-concept", "billing-pause"
PROJECT = RULES / RULE / "cases" / CASE / "project"


class BillingPauseTests(unittest.TestCase):
    def test_pause_on_subscription_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_membership_beside_subscription_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "the code names one concept twice: MAX_MEMBERSHIP_PAUSE, MembershipPause, membership, membership_id, pause_membership beside "
                "Subscription, SubscriptionStatus, SubscriptionStore, cancel_subscription, subscription, subscription_id, subscriptions, "
                "test_active_subscription_past_its_date_is_due"
            ],
        )

    def test_full_rename_passes(self):
        answer = []
        for path in sorted(PROJECT.rglob("*.py")):
            relative = path.relative_to(PROJECT).as_posix()
            body = path.read_text().replace("Subscription", "Membership").replace("subscription", "membership")
            renamed = relative.replace("subscription", "membership")
            answer.append(f'<file path="{renamed}">\n{body}</file>')
            if renamed != relative:
                answer.append(f'<file path="{relative}">\n</file>')
        answer.append('<file path="billing/pause.py">\ndef pause_membership(membership):\n    return membership\n</file>')
        self.assertEqual(grade(RULE, CASE, text="\n".join(answer)), [])

    def test_no_pause_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Nothing to change."), ["no new name carries the pause"])
