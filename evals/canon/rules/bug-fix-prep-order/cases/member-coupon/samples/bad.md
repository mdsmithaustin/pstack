Both the cart page and checkout apply the coupon inside the member branch and again after it. Two commits. The first adds the failing repro. The second drops the inner coupon line in both places.

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
<file path="cart.py">
"""Line and cart totals for the cart page. Amounts are in cents."""


def cart_summary(items, member=False, coupon=None):
    lines = []
    for item in items:
        price = item["price_cents"]
        if member and item.get("member_price_cents") is not None:
            price = item["member_price_cents"]
        if coupon:
            price = price * (100 - coupon["percent"]) // 100
        lines.append({"sku": item["sku"], "total_cents": price * item["qty"]})
    return {"lines": lines, "total_cents": sum(line["total_cents"] for line in lines)}
</file>
<file path="checkout.py">
"""The amount we charge at checkout. Amounts are in cents."""


def amount_due(customer, items, coupon=None):
    amount = 0
    for item in items:
        unit = item["price_cents"]
        if customer["member"] and item.get("member_price_cents") is not None:
            unit = item["member_price_cents"]
        if coupon:
            unit = unit * (100 - coupon["percent"]) // 100
        amount += unit * item["qty"]
    return amount
</file>
</commit>
