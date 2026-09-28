import unittest

from checkout import amount_due

MUG = {"sku": "MUG", "price_cents": 1500, "member_price_cents": 1200, "qty": 2}
TEE = {"sku": "TEE", "price_cents": 2500, "qty": 1}


class AmountDueTest(unittest.TestCase):
    def test_guest_is_charged_list_price(self):
        self.assertEqual(amount_due({"id": "c-1", "member": False}, [MUG, TEE]), 5500)

    def test_member_is_charged_member_price(self):
        self.assertEqual(amount_due({"id": "c-2", "member": True}, [MUG, TEE]), 4900)


if __name__ == "__main__":
    unittest.main()
