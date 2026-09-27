"""Delivery dates for orders."""
import math
from datetime import timedelta


def checkout_promise(d, n):
    """Arrival date shown to the shopper at checkout.

    Marketing owns the one-day buffer and changes it for campaigns.
    """
    day = d
    remaining = n + 1
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def carrier_deadline(d, n):
    """Latest hand-off date to the carrier under contract clause 4.2.

    Changes only when legal renegotiates the carrier contract.
    """
    day = d
    remaining = n + 1
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day
