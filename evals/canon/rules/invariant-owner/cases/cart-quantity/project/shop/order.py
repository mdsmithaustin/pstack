from dataclasses import dataclass, field


@dataclass
class Line:
    sku: str
    unit_price_cents: int
    quantity: int


@dataclass
class Order:
    id: str
    lines: list[Line] = field(default_factory=list)
    total_cents: int = 0


def add_line(order: Order, sku: str, unit_price_cents: int, quantity: int) -> None:
    for line in order.lines:
        if line.sku == sku:
            line.quantity += quantity
            break
    else:
        order.lines.append(Line(sku, unit_price_cents, quantity))
    order.total_cents += unit_price_cents * quantity


def to_json(order: Order) -> dict:
    return {
        "id": order.id,
        "lines": [{"sku": line.sku, "unit_price_cents": line.unit_price_cents, "quantity": line.quantity} for line in order.lines],
        "total_cents": order.total_cents,
    }
