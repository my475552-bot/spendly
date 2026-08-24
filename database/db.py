"""SQLite helpers for Spendly.

All database access goes through this module — never open a connection with
``sqlite3.connect()`` elsewhere, or foreign key enforcement will be off.

Calling convention for routes::

    conn = get_db()
    try:
        ...
        conn.commit()      # writes only
    finally:
        conn.close()
"""

import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Read once, at import. Tests set SPENDLY_DB before importing this module so
# they never touch the real database; unset, the path is unchanged.
DB_PATH = os.environ.get("SPENDLY_DB",
                         os.path.join(BASE_DIR, "expense_tracker.db"))

# Fixed category list — the de-facto enum for expenses.category.
CATEGORIES = ("Food", "Transport", "Bills", "Health",
              "Entertainment", "Shopping", "Other")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
"""


def get_db():
    """Return a new SQLite connection with dict-like rows and FKs enabled.

    Rows come back as ``sqlite3.Row`` — they support ``row["name"]`` and
    index access and work directly in Jinja, but are not dicts (no ``.get()``,
    not JSON-serializable).

    The caller owns the connection and must close it.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Must run on a fresh connection: the pragma is a silent no-op inside an
    # open transaction, and SQLite disables foreign keys by default.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the users and expenses tables. Safe to call repeatedly."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert the demo user and sample expenses, once.

    Returns early if the users table already has rows, so repeated calls (the
    Werkzeug reloader runs startup twice) never duplicate data.
    """
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com",
             generate_password_hash("demo123")),
        )
        user_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO expenses"
            " (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, amount, category, day, description)
                for category, amount, day, description in _sample_expenses()
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email):
    """Return the user row for ``email``, or None if there is no match.

    The lookup is case-sensitive, exactly like the UNIQUE constraint on the
    column — callers must lowercase the email themselves first.

    The result is a ``sqlite3.Row``, not a dict (see ``get_db``).
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password_hash):
    """Insert a new user and return the new row's id.

    ``password_hash`` must already be hashed — this function never sees a
    plaintext password. Raises ``sqlite3.IntegrityError`` if the email is
    already taken; the caller decides how to report that.
    """
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        user_id = cur.lastrowid
        conn.commit()
        return user_id
    finally:
        conn.close()


def _sample_expenses():
    """Return (category, amount, YYYY-MM-DD, description) rows for this month.

    Dates are built from today so seeded data always lands in the current
    month. Only days 1-28 are used, so replace(day=...) is safe in February.
    """
    today = date.today()

    def day(number):
        return today.replace(day=number).isoformat()

    return [
        ("Food", 12.50, day(3), "Coffee and croissant"),
        ("Transport", 45.00, day(5), "Monthly metro pass"),
        ("Bills", 120.75, day(8), "Electricity bill"),
        ("Health", 60.00, day(11), "Pharmacy - prescription"),
        ("Entertainment", 18.99, day(14), "Cinema ticket"),
        ("Shopping", 89.90, day(17), "Running shoes"),
        ("Other", 25.00, day(21), "Gift for a friend"),
        ("Food", 34.20, day(25), "Grocery run"),
    ]
