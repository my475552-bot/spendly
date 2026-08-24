"""Shared pytest fixtures for Spendly.

The order of statements in this file is load-bearing. ``database.db`` reads
DB_PATH once, at import time, so SPENDLY_DB has to be in the environment
*before* anything imports it. pytest imports conftest before any test module,
so setting it at module level here is guaranteed to win.

This is also why the DB path is not a fixture: ``tmp_path``,
``tmp_path_factory`` and ``monkeypatch.setenv`` all run after collection-time
imports, far too late to change a constant that is already bound.
"""

import os
import tempfile

os.environ["SPENDLY_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="spendly-test-"), "test.db")

import pytest                                  # noqa: E402

import app as flask_app_module                 # noqa: E402
from database import db as db_module           # noqa: E402


@pytest.fixture(scope="session")
def app():
    """The Flask app, already pointed at the throwaway database."""
    flask_app_module.app.config["TESTING"] = True
    return flask_app_module.app


@pytest.fixture
def client(app):
    """A fresh test client per test, so no cookies bleed between them."""
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_db():
    """Truncate both tables and re-seed before every test.

    A fresh database *file* per test is impossible (DB_PATH is frozen at
    import), so this restores a fresh database *state* instead: every test
    starts with exactly the seeded demo user and their 8 expenses.
    """
    conn = db_module.get_db()
    try:
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM users")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('users', 'expenses')")
        conn.commit()
    finally:
        conn.close()

    db_module.seed_db()
    yield


@pytest.fixture
def db_conn():
    """An open connection for tests that assert directly on rows."""
    conn = db_module.get_db()
    try:
        yield conn
    finally:
        conn.close()
