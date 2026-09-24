"""Customer records from the accounts export."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    tier: str
    country: str
    tax_exempt: bool
    loyalty_years: int
    credit_cents: int
    street: str
    city: str
    postal_code: str


def load_customers(rows):
    return {row["id"]: Customer(**row) for row in rows}
