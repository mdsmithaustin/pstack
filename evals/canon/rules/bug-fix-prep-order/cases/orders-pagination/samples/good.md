`page_count` adds one page even when the last page is already full. Two commits. The first adds the failing repro. The second rounds up instead.

<commit message="Add failing repro for an exact multiple of the page size">
<file path="tests/test_pagination.py">
import unittest

from pagination import page_count, page_slice


class PaginationTest(unittest.TestCase):
    def test_partial_last_page_counts_as_a_page(self):
        self.assertEqual(page_count(45, 20), 3)

    def test_full_last_page_adds_no_empty_page(self):
        self.assertEqual(page_count(40, 20), 2)

    def test_second_page_holds_the_next_items(self):
        self.assertEqual(page_slice(list(range(45)), 2, 20), list(range(20, 40)))


if __name__ == "__main__":
    unittest.main()
</file>
</commit>

<commit message="Round page count up instead of always adding a page">
<file path="pagination.py">
"""Paging for the orders list. Pages are numbered from 1."""


def page_count(total, per_page):
    return -(-total // per_page)


def page_slice(items, page, per_page):
    start = (page - 1) * per_page
    return items[start:start + per_page]
</file>
</commit>
