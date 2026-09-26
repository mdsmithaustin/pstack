<file path="tests/test_users.py">
import unittest

from accounts.users import DuplicateEmail, find_user_by_email, open_db, register


class RegisterTest(unittest.TestCase):
    def setUp(self):
        self.conn = open_db()

    def test_register_saves_name(self):
        register(self.conn, "bo@example.com", "Bo")

        row = self.conn.execute(
            "SELECT name FROM users WHERE email = ?", ("bo@example.com",)
        ).fetchone()
        self.assertEqual(row, ("Bo",))

    def test_second_registration_with_same_email_is_refused(self):
        register(self.conn, "bo@example.com", "Bo")

        with self.assertRaises(DuplicateEmail):
            register(self.conn, "bo@example.com", "Robert")

    def test_mixed_case_email_is_found_by_its_lowercase_form(self):
        register(self.conn, "Ann@Example.COM", "Ann")

        user = find_user_by_email(self.conn, "ann@example.com")

        self.assertEqual(user.email, "ann@example.com")


if __name__ == "__main__":
    unittest.main()
</file>
