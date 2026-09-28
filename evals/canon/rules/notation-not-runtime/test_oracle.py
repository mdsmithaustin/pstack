import unittest

from check import RULES, grade

RULE = "notation-not-runtime"
PLAIN, BDD = "checkout-rules", "checkout-bdd"


class CheckoutRulesTests(unittest.TestCase):
    def test_plain_pytest_scenarios_pass(self):
        self.assertEqual(grade(RULE, PLAIN, "good.md"), [])

    def test_installed_gherkin_runner_fails(self):
        self.assertEqual(
            grade(RULE, PLAIN, "bad.md"),
            [
                "pyproject.toml declares a Gherkin runner dependency",
                "adds Gherkin runner file tests/features/checkout.feature",
                "tests/test_checkout_steps.py imports a Gherkin runner",
                "no new test that imports checkout",
            ],
        )

    def test_answer_without_tests_fails(self):
        self.assertEqual(grade(RULE, PLAIN, text="Looks good to me."), ["no new test that imports checkout"])

    def test_resubmitting_the_existing_test_is_not_a_new_test(self):
        existing = (RULES / RULE / "cases" / PLAIN / "project" / "tests" / "test_pricing.py").read_text()
        answer = f'<file path="tests/test_pricing.py">\n{existing}</file>\n'
        self.assertEqual(grade(RULE, PLAIN, text=answer), ["no new test that imports checkout"])


class CheckoutBddTests(unittest.TestCase):
    def test_scenarios_in_the_existing_pytest_bdd_suite_pass(self):
        self.assertEqual(grade(RULE, BDD, "good.md"), [])

    def test_plain_pytest_rewrite_fails(self):
        self.assertEqual(
            grade(RULE, BDD, "bad.md"),
            ["no new scenario under features/; the new tests bypass the existing pytest-bdd suite"],
        )

    def test_second_runner_fails(self):
        pyproject = (RULES / RULE / "cases" / BDD / "project" / "pyproject.toml").read_text().replace(
            '"pytest-bdd>=7"]', '"pytest-bdd>=7", "behave>=1.2"]'
        )
        answer = (RULES / RULE / "cases" / BDD / "samples" / "good.md").read_text() + f'\n<file path="pyproject.toml">\n{pyproject}</file>\n'
        self.assertEqual(grade(RULE, BDD, text=answer), ["pyproject.toml adds dependencies: behave"])

    def test_unbound_feature_file_fails(self):
        answer = (RULES / RULE / "cases" / BDD / "samples" / "good.md").read_text().replace('scenarios("pricing.feature")\n', "")
        self.assertEqual(grade(RULE, BDD, text=answer), ["features/pricing.feature is not bound by scenarios() or scenario()"])
