import unittest

from accounts.users import DuplicateEmail, open_db, register


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


if __name__ == "__main__":
    unittest.main()
