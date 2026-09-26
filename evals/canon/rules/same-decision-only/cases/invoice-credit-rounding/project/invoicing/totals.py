"""Totals printed on invoices and credit notes."""
from decimal import ROUND_HALF_EVEN, Decimal


def invoice_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = sum((price * quantity for price, quantity in lines), Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    vat = (net * vat_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return net + vat


def credit_note_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = sum((price * quantity for price, quantity in lines), Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    vat = (net * vat_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return -(net + vat)
