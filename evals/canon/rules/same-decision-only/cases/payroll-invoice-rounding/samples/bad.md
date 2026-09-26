Both modules defined the same `round_money`. It now lives once in `money.py`, and both import it.

<file path="money.py">
"""Money helpers shared across the back office."""
from decimal import ROUND_HALF_UP, Decimal


def round_money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
</file>

<file path="payroll/pay.py">
"""Monthly net pay for the provider's pay file."""
from decimal import Decimal

from money import round_money


def net_pay(gross: Decimal, tax_rate: Decimal, pension_rate: Decimal) -> Decimal:
    tax = round_money(gross * tax_rate)
    pension = round_money(gross * pension_rate)
    return round_money(gross - tax - pension)
</file>

<file path="invoicing/totals.py">
"""Totals printed on customer invoices."""
from decimal import Decimal

from money import round_money


def invoice_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = round_money(sum((price * quantity for price, quantity in lines), Decimal("0")))
    vat = round_money(net * vat_rate)
    return net + vat
</file>
