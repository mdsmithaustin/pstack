from dataclasses import dataclass, field


@dataclass
class LineItem:
    sku: str
    quantity: int
    unit_cents: int

    @property
    def total_cents(self):
        return self.quantity * self.unit_cents


@dataclass
class Order:
    id: str
    status: str
    line_items: list = field(default_factory=list)
    refunded_cents: int = 0

    @property
    def total_cents(self):
        return sum(item.total_cents for item in self.line_items)
