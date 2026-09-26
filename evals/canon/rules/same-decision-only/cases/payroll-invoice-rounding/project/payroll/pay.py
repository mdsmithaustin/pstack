"""Monthly net pay for the provider's pay file."""
from decimal import ROUND_HALF_UP, Decimal


def round_money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def net_pay(gross: Decimal, tax_rate: Decimal, pension_rate: Decimal) -> Decimal:
    tax = round_money(gross * tax_rate)
    pension = round_money(gross * pension_rate)
    return round_money(gross - tax - pension)
