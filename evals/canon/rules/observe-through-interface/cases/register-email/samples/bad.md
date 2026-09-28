<file path="tests/test_register_email.py">
import unittest

from accounts.users import open_db, register


class RegisterEmailTest(unittest.TestCase):
    def test_register_stores_email_lowercased(self):
        conn = open_db()
        register(conn, "Ann@Example.COM", "Ann")

        row = conn.execute("SELECT email FROM users WHERE name = ?", ("Ann",)).fetchone()

        self.assertEqual(row, ("ann@example.com",))


if __name__ == "__main__":
    unittest.main()
</file>
