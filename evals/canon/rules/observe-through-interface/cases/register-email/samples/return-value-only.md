<file path="tests/test_register_email.py">
import unittest

from accounts.users import open_db, register


class RegisterEmailTest(unittest.TestCase):
    def test_register_returns_lowercased_email(self):
        user = register(open_db(), "Ann@Example.COM", "Ann")

        self.assertEqual(user.email, "ann@example.com")


if __name__ == "__main__":
    unittest.main()
</file>
