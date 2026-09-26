The two `round_money` helpers match today, but they are not one decision. Payroll rounding follows the provider's import spec and HR changes it. Invoice rounding follows the tax rules and finance changes it. A shared helper would make a change for one team silently change the other's figures. I kept them apart and named each after its owner so the next reader sees why.

<file path="payroll/pay.py">
"""Monthly net pay for the provider's pay file."""
from decimal import ROUND_HALF_UP, Decimal


def round_pay(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def net_pay(gross: Decimal, tax_rate: Decimal, pension_rate: Decimal) -> Decimal:
    tax = round_pay(gross * tax_rate)
    pension = round_pay(gross * pension_rate)
    return round_pay(gross - tax - pension)
</file>

<file path="invoicing/totals.py">
"""Totals printed on customer invoices."""
from decimal import ROUND_HALF_UP, Decimal


def round_invoice_amount(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def invoice_total(lines: list[tuple[Decimal, int]], vat_rate: Decimal) -> Decimal:
    net = round_invoice_amount(sum((price * quantity for price, quantity in lines), Decimal("0")))
    vat = round_invoice_amount(net * vat_rate)
    return net + vat
</file>
