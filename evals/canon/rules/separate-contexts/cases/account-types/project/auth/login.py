import hashlib

from auth.account import Account


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(account: Account, password: str) -> bool:
    return account.password_hash == hash_password(password)


def needs_second_factor(account: Account) -> bool:
    return account.mfa_enabled
