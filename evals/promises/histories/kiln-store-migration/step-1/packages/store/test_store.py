import tempfile
import unittest

from store import Store


class StoreTest(unittest.TestCase):
    def test_put_then_get_round_trips(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            self.assertEqual(store.put("tags", "ops.txt", "a\n"), 2)
            self.assertEqual(store.get("tags", "ops.txt"), "a\n")
            self.assertEqual(store.keys("tags"), ["ops.txt"])

    def test_missing_kind_has_no_keys(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(Store(root).keys("tags"), [])


if __name__ == "__main__":
    unittest.main()
