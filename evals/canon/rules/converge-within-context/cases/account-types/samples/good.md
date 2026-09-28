These two types are not duplicates. `billing.account.Account` is the payer that gets charged, and `auth.account.Account` is the sign-in identity. They share only the id, so I kept them apart, named each for what it is, and gave them one shared `AccountId`.

<file path="accounts_common.py">
from typing import NewType

AccountId = NewType("AccountId", str)
</file>

<file path="billing/account.py">
from dataclasses import dataclass

from accounts_common import AccountId


@dataclass(frozen=True)
class Account:
    id: AccountId
    payer_name: str
    balance_cents: int
</file>

<file path="auth/account.py">
from dataclasses import dataclass

from accounts_common import AccountId


@dataclass(frozen=True)
class Account:
    id: AccountId
    email: str
    password_hash: str
    mfa_enabled: bool
</file>
