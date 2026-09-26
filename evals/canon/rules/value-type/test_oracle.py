import unittest

from check import RULES, grade

RULE, CASE = "value-type", "marketplace-subtotal"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class MarketplaceSubtotalTests(unittest.TestCase):
    def test_per_currency_money_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_summed_cents_fail(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            ["a cart with a EUR line and a USD line gets one amount as its subtotal: '37.99'"],
        )

    def test_raising_on_mixed_currency_passes(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "totals[amount.currency] = totals[amount.currency] + amount if amount.currency in totals else amount",
            "totals = {\"all\": totals[\"all\"] + amount if totals else amount}",
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_money_object_with_one_currency_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "def __add__(self, other: \"Money\") -> \"Money\":\n        if other.currency != self.currency:",
            "def __add__(self, other: \"Money\") -> \"Money\":\n        if False:",
        ).replace('"subtotal": subtotal(cart),', '"subtotal": sum((Money(l.price.amount_cents, l.price.currency) for l in cart.lines[1:]), Money(cart.lines[0].price.amount_cents, cart.lines[0].price.currency)),')
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            [
                "the subtotal of a EUR-only cart is Money(amount_cents=3298, currency='EUR'), expected 45.97 EUR",
                "a cart with a EUR line and a USD line gets one amount as its subtotal: Money(amount_cents=3799, currency='EUR')",
            ],
        )

    def test_no_subtotal_fails(self):
        self.assertEqual(grade(RULE, CASE, text="No change."), ["the summary has no subtotal"])
