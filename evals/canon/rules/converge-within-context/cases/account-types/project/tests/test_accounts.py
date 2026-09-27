import unittest

from auth.account import Account as LoginAccount
from auth.login import check_password, hash_password
from billing.account import Account as BillingAccount
from billing.invoices import charge


class AccountTest(unittest.TestCase):
    def test_charge_lowers_the_balance(self):
        account = BillingAccount("a1", "Ada Lovelace", 5000)
        self.assertEqual(charge(account, 1200).balance_cents, 3800)

    def test_password_check(self):
        account = LoginAccount("a1", "ada@example.com", hash_password("pw"), False)
        self.assertTrue(check_password(account, "pw"))
