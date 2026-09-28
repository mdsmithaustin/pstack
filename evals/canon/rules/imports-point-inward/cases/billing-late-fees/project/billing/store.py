"""SQLite storage for customers and invoices."""
import os
import sqlite3

SCHEMA = """
create table if not exists customers (
    id text primary key,
    flagged integer not null default 0
);
create table if not exists invoices (
    number text primary key,
    customer_id text not null references customers(id),
    amount text not null,
    paid text not null default '0.00',
    due text not null
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ.get("BILLING_DB", "billing.sqlite3"))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def load_invoice(number: str) -> sqlite3.Row:
    with connect() as conn:
        row = conn.execute("select * from invoices where number = ?", (number,)).fetchone()
    if row is None:
        raise KeyError(number)
    return row


def open_invoices() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("select * from invoices where cast(paid as real) < cast(amount as real) order by due").fetchall()


def is_flagged(customer_id: str) -> bool:
    with connect() as conn:
        row = conn.execute("select flagged from customers where id = ?", (customer_id,)).fetchone()
    return bool(row and row["flagged"])
