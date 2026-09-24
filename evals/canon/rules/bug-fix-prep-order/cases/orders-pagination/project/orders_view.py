"""Data for the orders list page."""
from pagination import page_count, page_slice

PER_PAGE = 20


def orders_page(orders, page):
    return {
        "orders": page_slice(orders, page, PER_PAGE),
        "page": page,
        "pages": page_count(len(orders), PER_PAGE),
    }
