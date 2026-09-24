The two functions are identical, so both now call one business-day helper.

<commit message="Extract Function: add_business_days for the duplicated date loops">
<file path="shipping/promises.py">
"""Delivery dates for orders."""
from datetime import timedelta


def add_business_days(start, count):
    day = start
    remaining = count
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def checkout_promise(order_date, warehouse_days):
    """Arrival date shown to the shopper at checkout."""
    return add_business_days(order_date, warehouse_days + 1)


def carrier_deadline(order_date, warehouse_days):
    """Latest hand-off date to the carrier under contract clause 4.2."""
    return add_business_days(order_date, warehouse_days + 1)
</file>
</commit>
