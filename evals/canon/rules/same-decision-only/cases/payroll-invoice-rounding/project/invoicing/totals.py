"""Totals printed on customer invoices."""
from decimal import ROUND_HALF_UP, Decimal


def round_money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def invoice_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = round_money(sum((price * quantity for price, quantity in lines), Decimal("0")))
    vat = round_money(net * vat_rate)
    return net + vat
