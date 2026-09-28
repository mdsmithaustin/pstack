<file path="accounts.py">
from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    id: str
    payer_name: str | None = None
    balance_cents: int | None = None
    email: str | None = None
    password_hash: str | None = None
    mfa_enabled: bool = False
</file>

<file path="billing/account.py">
from accounts import Account
</file>

<file path="auth/account.py">
from accounts import Account
</file>
