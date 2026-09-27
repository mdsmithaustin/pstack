import unittest

from pagination import page_count, page_slice


class PaginationTest(unittest.TestCase):
    def test_partial_last_page_counts_as_a_page(self):
        self.assertEqual(page_count(45, 20), 3)

    def test_second_page_holds_the_next_items(self):
        self.assertEqual(page_slice(list(range(45)), 2, 20), list(range(20, 40)))


if __name__ == "__main__":
    unittest.main()
