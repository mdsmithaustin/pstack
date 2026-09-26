from dataclasses import replace

from billing.account import Account


def charge(account: Account, amount_cents: int) -> Account:
    return replace(account, balance_cents=account.balance_cents - amount_cents)


def statement_line(account: Account) -> str:
    return f"{account.payer_name}: {account.balance_cents / 100:.2f}"
