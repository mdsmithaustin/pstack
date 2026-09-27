from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    id: str
    payer_name: str
    balance_cents: int
