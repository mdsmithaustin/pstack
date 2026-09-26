The cart page and checkout each carry a copy of the same pricing loop, and both copies apply the coupon inside the member branch and again after it. Three commits. The first moves the per-unit price into one function with every total unchanged. The second adds the failing repro. The third fixes the one function.

<commit message="Move per-unit pricing into one function">
<file path="pricing.py">
"""Per-unit price after member pricing and coupons. Amounts are in cents."""


def unit_price(item, member=False, coupon=None):
    price = item["price_cents"]
    if member and item.get("member_price_cents") is not None:
        price = item["member_price_cents"]
        if coupon:
            price = price * (100 - coupon["percent"]) // 100
    if coupon:
        price = price * (100 - coupon["percent"]) // 100
    return price
</file>
<file path="cart.py">
"""Line and cart totals for the cart page. Amounts are in cents."""
from pricing import unit_price


def cart_summary(items, member=False, coupon=None):
    lines = [
        {"sku": item["sku"], "total_cents": unit_price(item, member, coupon) * item["qty"]}
        for item in items
    ]
    return {"lines": lines, "total_cents": sum(line["total_cents"] for line in lines)}
</file>
<file path="checkout.py">
"""The amount we charge at checkout. Amounts are in cents."""
from pricing import unit_price


def amount_due(customer, items, coupon=None):
    return sum(unit_price(item, customer["member"], coupon) * item["qty"] for item in items)
</file>
</commit>

<commit message="Add failing repro for coupons on member prices">
<file path="tests/test_member_coupon.py">
import unittest

from cart import cart_summary
from checkout import amount_due

MUG = {"sku": "MUG", "price_cents": 1500, "member_price_cents": 1200, "qty": 2}
COUPON = {"code": "SAVE10", "percent": 10}


class MemberCouponTest(unittest.TestCase):
    def test_cart_takes_the_coupon_off_the_member_price_once(self):
        self.assertEqual(cart_summary([MUG], member=True, coupon=COUPON)["total_cents"], 2160)

    def test_checkout_charges_the_coupon_off_the_member_price_once(self):
        self.assertEqual(amount_due({"id": "c-3", "member": True}, [MUG], coupon=COUPON), 2160)


if __name__ == "__main__":
    unittest.main()
</file>
</commit>

<commit message="Apply the coupon once on member prices">
<file path="pricing.py">
"""Per-unit price after member pricing and coupons. Amounts are in cents."""


def unit_price(item, member=False, coupon=None):
    price = item["price_cents"]
    if member and item.get("member_price_cents") is not None:
        price = item["member_price_cents"]
    if coupon:
        price = price * (100 - coupon["percent"]) // 100
    return price
</file>
</commit>
