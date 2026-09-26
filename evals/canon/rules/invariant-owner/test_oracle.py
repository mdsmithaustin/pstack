import unittest

from check import RULES, grade

RULE, CASE = "invariant-owner", "cart-quantity"
SAMPLES = RULES / RULE / "cases" / CASE / "samples"


class CartQuantityTests(unittest.TestCase):
    def test_operation_on_the_order_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_route_mutating_a_line_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "shop/routes/cart.py indexes into .lines[",
                "shop/routes/cart.py assigns .quantity",
                "total_cents is 1500 after the change, expected 2250",
            ],
        )

    def test_route_recomputing_the_total_fails_on_shape_alone(self):
        answer = (SAMPLES / "bad.md").read_text().replace(
            "    return 200, orders.to_json(order)\n\n\nROUTES",
            "    order.total_cents = sum(l.unit_price_cents * l.quantity for l in order.lines)\n    return 200, orders.to_json(order)\n\n\nROUTES",
        )
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            [
                "shop/routes/cart.py indexes into .lines[",
                "shop/routes/cart.py assigns .total_cents",
                "shop/routes/cart.py assigns .quantity",
            ],
        )

    def test_missing_route_fails(self):
        self.assertEqual(
            grade(RULE, CASE, text="No change."),
            ["PATCH /cart/o1/lines/MUG answered 404", "MUG quantity is [2] after the change, expected [5]", "total_cents is 1500 after the change, expected 2250"],
        )
