The two date loops look like Duplicated Code, but marketing changes the checkout promise and legal changes the carrier deadline, so they stay separate. The real problems are the unused `math` import and the parameter names `d` and `n`.

<commit message="Remove the unused math import and rename d, n in promises.py (Rename Variable)">
<file path="shipping/promises.py">
"""Delivery dates for orders."""
from datetime import timedelta


def checkout_promise(order_date, warehouse_days):
    """Arrival date shown to the shopper at checkout.

    Marketing owns the one-day buffer and changes it for campaigns.
    """
    day = order_date
    remaining = warehouse_days + 1
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def carrier_deadline(order_date, warehouse_days):
    """Latest hand-off date to the carrier under contract clause 4.2.

    Changes only when legal renegotiates the carrier contract.
    """
    day = order_date
    remaining = warehouse_days + 1
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day
</file>
</commit>
