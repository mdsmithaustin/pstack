from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Shipment:
    id: str
    order_id: str
    carrier: str
    promised_date: date
    delivered_at: date | None = None

    @property
    def arrived(self) -> bool:
        return self.delivered_at is not None
