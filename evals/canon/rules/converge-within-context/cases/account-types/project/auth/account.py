from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    id: str
    email: str
    password_hash: str
    mfa_enabled: bool
