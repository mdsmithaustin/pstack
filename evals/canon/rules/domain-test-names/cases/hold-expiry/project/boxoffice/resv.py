from dataclasses import dataclass
from datetime import datetime, timedelta

RESV_TTL = timedelta(seconds=900)


@dataclass
class Resv:
    seats: tuple
    created_at: datetime
    paid: bool = False


def create_resv(seats, now):
    return Resv(tuple(seats), now)


def pay_resv(resv):
    resv.paid = True


def resv_status(resv, now):
    if resv.paid:
        return "booked"
    if now - resv.created_at >= RESV_TTL:
        return "expired"
    return "active"
