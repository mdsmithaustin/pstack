import unittest

from check import RULES, grade

RULE, CASE = "route-codebase-design", "pricing-modules"
GOOD = (RULES / RULE / "cases" / CASE / "samples" / "good.md").read_text(encoding="utf-8")


class PricingModulesTests(unittest.TestCase):
    def test_deep_module_with_in_memory_adapter_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_facade_over_the_shallow_modules_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "6 test(s) on the shallow modules kept: test_amount_becomes_cents_and_currency_uppercases, test_fetch_reads_the_price_json, "
                "test_missing_currency_is_invalid, test_negative_amount_is_invalid, test_put_then_get_returns_the_price, test_unknown_sku_misses",
                "no in-memory adapter for the pricing service",
                "tests/test_cache.py mocks instead of using an adapter",
                "tests/test_fetcher.py mocks instead of using an adapter",
                "tests/test_mapper.py mocks instead of using an adapter",
                "tests/test_service.py mocks instead of using an adapter",
            ],
        )

    def test_changed_output_fails_the_pin(self):
        changed = GOOD.replace('raw["currency"].upper()', 'raw["currency"]')

        self.assertEqual(
            grade(RULE, CASE, text=changed),
            ["checkout, quotes, or catalog export behave differently against the same pricing responses", "final suite fails"],
        )

    def test_kept_layered_file_fails_without_its_delete_tag(self):
        kept = GOOD.replace('<delete path="tests/test_validator.py"/>\n', "")

        self.assertEqual(
            grade(RULE, CASE, text=kept),
            ["2 test(s) on the shallow modules kept: test_missing_currency_is_invalid, test_negative_amount_is_invalid", "final suite fails"],
        )


if __name__ == "__main__":
    unittest.main()
