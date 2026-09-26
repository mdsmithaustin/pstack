import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str


class DuplicateEmail(Exception):
    pass


def open_db(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def register(conn: sqlite3.Connection, email: str, name: str) -> User:
    normalized = email.strip().lower()
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, name) VALUES (?, ?)", (normalized, name)
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateEmail(normalized) from exc
    conn.commit()
    return User(cursor.lastrowid, normalized, name)


def find_user_by_email(conn: sqlite3.Connection, email: str) -> User | None:
    row = conn.execute(
        "SELECT id, email, name FROM users WHERE email = ?", (email,)
    ).fetchone()
    return User(*row) if row else None
