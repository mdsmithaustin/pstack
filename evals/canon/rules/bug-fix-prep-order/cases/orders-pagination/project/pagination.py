"""Paging for the orders list. Pages are numbered from 1."""


def page_count(total, per_page):
    return total // per_page + 1


def page_slice(items, page, per_page):
    start = (page - 1) * per_page
    return items[start:start + per_page]
