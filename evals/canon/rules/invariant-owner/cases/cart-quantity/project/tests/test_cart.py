import unittest

from shop.app import handle
from shop.store import OrderStore


class CartTest(unittest.TestCase):
    def test_adding_items_updates_the_total(self):
        store = OrderStore()
        handle(store, "POST", "/cart/o1/lines", {"sku": "MUG", "unit_price_cents": 250, "quantity": 2})
        status, cart = handle(store, "POST", "/cart/o1/lines", {"sku": "MUG", "unit_price_cents": 250, "quantity": 1})
        self.assertEqual((status, cart["total_cents"]), (201, 750))
