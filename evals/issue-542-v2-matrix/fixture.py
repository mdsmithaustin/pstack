"""Build the throwaway `shop` repository every row runs in: three commits whose messages carry the reasons a `why` question asks about."""

import subprocess
from pathlib import Path

GIT = ["git", "-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]

PRICING = '''"""Line pricing."""


def line_total(unit_cents, quantity):
    return unit_cents * quantity
'''

TAX_V1 = '''"""Sales tax."""


def order_tax(subtotal_cents, rate_bp):
    return round(subtotal_cents * rate_bp / 10000)
'''

TAX_V2 = '''"""Sales tax, rounded per line item.

Finance reconciles invoices line by line, so each line rounds half up on its own.
"""


def line_tax(line_cents, rate_bp):
    return (line_cents * rate_bp + 5000) // 10000


def order_tax(line_totals, rate_bp):
    return sum(line_tax(line, rate_bp) for line in line_totals)
'''

DISCOUNTS_V1 = '''"""Discounts."""


def apply_discounts(subtotal_cents, percents):
    total = subtotal_cents
    for percent in percents:
        total -= total * percent // 100
    return total
'''

DISCOUNTS_V3 = '''"""Discounts, capped at 30 percent of the subtotal."""

MAX_DISCOUNT_PERCENT = 30


def apply_discounts(subtotal_cents, percents):
    total = subtotal_cents
    for percent in percents:
        total -= total * percent // 100
    floor = subtotal_cents * (100 - MAX_DISCOUNT_PERCENT) // 100
    return max(total, floor)
'''

ORDERS_V1 = '''"""Order totals."""

from shop.discounts import apply_discounts
from shop.pricing import line_total
from shop.tax import order_tax


def order_total(items, rate_bp, discount_percents=()):
    subtotal = sum(line_total(unit, qty) for unit, qty in items)
    discounted = apply_discounts(subtotal, discount_percents)
    return discounted + order_tax(discounted, rate_bp)
'''

ORDERS_V2 = '''"""Order totals."""

from shop.discounts import apply_discounts
from shop.pricing import line_total
from shop.tax import order_tax


def order_total(items, rate_bp, discount_percents=()):
    lines = [line_total(unit, qty) for unit, qty in items]
    discounted = apply_discounts(sum(lines), discount_percents)
    return discounted + order_tax(lines, rate_bp)
'''

TESTS = '''import unittest

from shop.orders import order_total


class OrderTotal(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual(order_total([(1000, 2)], 800), 2160)

    def test_discount(self):
        self.assertEqual(order_total([(1000, 2)], 0, [10]), 1800)


if __name__ == "__main__":
    unittest.main()
'''

README = """# shop

Order totals for the storefront: line pricing, discounts, then sales tax.

Run the tests with `python3 -m unittest discover -s tests -t .`.
"""

HISTORY = [
    ("Add pricing and order totals", {"shop/__init__.py": "", "shop/pricing.py": PRICING, "shop/tax.py": TAX_V1,
                                      "shop/discounts.py": DISCOUNTS_V1, "shop/orders.py": ORDERS_V1,
                                      "tests/__init__.py": "", "tests/test_orders.py": TESTS, "README.md": README}),
    ("Round tax per line item, half up, instead of once on the order\n\nFinance reconciles invoices line by line and the order-level rounding\ndrifted by up to 3 cents on large carts (SHOP-212).",
     {"shop/tax.py": TAX_V2, "shop/orders.py": ORDERS_V2}),
    ("Cap stacked discounts at 30 percent of the subtotal\n\nThe partner promo stacked with loyalty and produced a negative total (SHOP-231).",
     {"shop/discounts.py": DISCOUNTS_V3}),
]


def build(dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run([*GIT, "-C", str(dest), "init", "-q", "-b", "main"], check=True)
    for message, files in HISTORY:
        for rel, text in files.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        subprocess.run([*GIT, "-C", str(dest), "add", "-A"], check=True)
        subprocess.run([*GIT, "-C", str(dest), "commit", "-qm", message], check=True)
