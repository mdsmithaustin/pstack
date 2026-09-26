import unittest

from check import RULES, grade

RULE, CASE = "declarative-steps", "paid-articles"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class PaidArticlesTests(unittest.TestCase):
    def test_helper_steps_pass(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_inline_environ_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "tests.test_paywall:test_free_subscriber_cannot_open_paid_article builds the request inline: "
                "Bearer token, HTTP_ header, PATH_INFO, REQUEST_METHOD, direct app call, environ, "
                "setup_testing_defaults, start_response, wsgi.input"
            ],
        )

    def test_new_helper_outside_the_test_body_passes(self):
        answer = (SAMPLES / "good.md").read_text().replace(
            "class ArticlesTest(unittest.TestCase):",
            "def open_as(token, slug):\n"
            "    environ = {\"REQUEST_METHOD\": \"GET\", \"PATH_INFO\": f\"/articles/{slug}\", \"HTTP_AUTHORIZATION\": f\"Bearer {token}\"}\n"
            "    setup_testing_defaults(environ)\n"
            "    return b\"\".join(app(environ, lambda status, headers: None))\n\n\n"
            "class ArticlesTest(unittest.TestCase):",
        )
        self.assertEqual(grade(RULE, CASE, text=answer), [])

    def test_answer_without_tests_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Done."), ["no new test in the answer"])
