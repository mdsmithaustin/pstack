from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Order:
    id: str
    total_cents: int
    delivered_on: Optional[date] = None
