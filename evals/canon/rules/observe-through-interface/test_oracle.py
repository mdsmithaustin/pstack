import unittest

from check import RULES, grade

RULE, CASE = "observe-through-interface", "register-email"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class RegisterEmailTests(unittest.TestCase):
    def test_lookup_through_public_function_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_sql_readback_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            ["tests.test_register_email:RegisterEmailTest.test_register_stores_email_lowercased reads storage directly"],
        )

    def test_return_value_alone_misses_what_was_stored(self):
        self.assertEqual(
            grade(RULE, CASE, "return-value-only.md"),
            ["new tests still pass when the code stores raw returns normalized"],
        )

    def test_test_that_fails_on_working_code_fails(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            'self.assertEqual(user.email, "ann@example.com")', 'self.assertEqual(user.email, "Ann@Example.COM")'
        )
        self.assertIn(
            "tests.test_users:RegisterTest.test_mixed_case_email_is_found_by_its_lowercase_form fails against the working code",
            grade(RULE, CASE, text=answer),
        )
