import unittest

from cart import cart_summary

MUG = {"sku": "MUG", "price_cents": 1500, "member_price_cents": 1200, "qty": 2}
TEE = {"sku": "TEE", "price_cents": 2500, "qty": 1}


class CartSummaryTest(unittest.TestCase):
    def test_guest_pays_list_price(self):
        self.assertEqual(cart_summary([MUG, TEE])["total_cents"], 5500)

    def test_member_pays_member_price(self):
        self.assertEqual(cart_summary([MUG, TEE], member=True)["total_cents"], 4900)

    def test_guest_coupon_takes_percent_off(self):
        self.assertEqual(cart_summary([MUG, TEE], coupon={"code": "SAVE10", "percent": 10})["total_cents"], 4950)


if __name__ == "__main__":
    unittest.main()
