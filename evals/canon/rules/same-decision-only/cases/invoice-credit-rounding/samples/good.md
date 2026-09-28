A credit note reverses invoice lines under the same tax rules, so both totals make one rounding decision. It now lives in one helper.

<file path="invoicing/totals.py">
"""Totals printed on invoices and credit notes."""
from decimal import ROUND_HALF_EVEN, Decimal


def round_tax(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def invoice_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = round_tax(sum((price * quantity for price, quantity in lines), Decimal("0")))
    return net + round_tax(net * vat_rate)


def credit_note_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    return -invoice_total(lines, vat_rate)
</file>
