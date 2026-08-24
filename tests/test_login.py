"""Tests for Step 3 — login and logout.

Credentials come from conftest.reset_db, which re-seeds the demo user before
every test, so VALID below must stay in sync with seed_db().

Session assertions use ``client.session_transaction()``: it opens the client's
own cookie jar outside a request, which is the only way to read or seed
``session`` without a live request context.
"""

import os

import pytest
from flask import url_for

from app import (INVALID_CREDENTIALS_ERROR, MISSING_CREDENTIALS_ERROR,
                 _validate_login, login_required)
from database import db as db_module

VALID = {
    "email": "demo@spendly.com",
    "password": "demo123",
}

TEMPLATE_DIR = os.path.join(db_module.BASE_DIR, "templates")


def _post(client, **overrides):
    """POST the valid payload with any field replaced or removed."""
    data = dict(VALID)
    data.update(overrides)
    return client.post("/login", data=data)


def _login(client):
    """Sign in as the seeded demo user."""
    return _post(client)


def _demo_id(conn):
    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (VALID["email"],)
    ).fetchone()["id"]


# ------------------------------------------------------------------ #
# Test isolation                                                      #
# ------------------------------------------------------------------ #

def test_tests_do_not_touch_the_real_database():
    """conftest must have redirected DB_PATH away from the real file."""
    real_db = os.path.join(db_module.BASE_DIR, "expense_tracker.db")
    assert db_module.DB_PATH != real_db
    assert "spendly-test-" in db_module.DB_PATH


# ------------------------------------------------------------------ #
# GET /login                                                          #
# ------------------------------------------------------------------ #

def test_get_login_returns_200(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b'name="password"' in response.data


def test_get_login_has_no_error_box(client):
    response = client.get("/login")
    assert b"auth-error" not in response.data


def test_get_login_has_empty_email_field(client):
    """The sticky value must default to empty, not to Undefined."""
    response = client.get("/login")
    assert b'value=""' in response.data


def test_login_template_has_no_hardcoded_action():
    """DoD 9. url_for and a literal path render identically over HTTP, so the
    only way to assert this is against the template source."""
    path = os.path.join(TEMPLATE_DIR, "login.html")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert 'action="/login"' not in source
    assert "url_for('login')" in source


# ------------------------------------------------------------------ #
# Successful sign-in                                                  #
# ------------------------------------------------------------------ #

def test_valid_login_redirects_to_landing(client):
    response = _login(client)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_valid_login_sets_session_user_id(client, db_conn):
    _login(client)
    with client.session_transaction() as sess:
        assert sess["user_id"] == _demo_id(db_conn)


def test_valid_login_flashes_welcome_message(client):
    response = client.post("/login", data=VALID, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome back, Demo User." in response.data


def test_valid_login_shows_logged_in_navbar(client):
    response = client.post("/login", data=VALID, follow_redirects=True)
    assert b"Sign out" in response.data
    assert b"Get started" not in response.data


def test_login_email_is_case_insensitive(client):
    """SQLite UNIQUE is case-sensitive, so this only passes if the route
    lowercases before the lookup."""
    response = _post(client, email="DEMO@SPENDLY.COM")
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_login_email_is_stripped(client):
    response = _post(client, email="  demo@spendly.com  ")
    assert response.status_code == 302


def test_login_clears_stale_session_keys(client):
    """Proves session.clear() runs *before* the user_id assignment."""
    with client.session_transaction() as sess:
        sess["stale"] = "should not survive"

    _login(client)

    with client.session_transaction() as sess:
        assert "stale" not in sess
        assert "user_id" in sess


# ------------------------------------------------------------------ #
# Failed sign-in                                                      #
# ------------------------------------------------------------------ #

def test_wrong_password_returns_401(client):
    response = _post(client, password="wrongpassword")
    assert response.status_code == 401
    assert INVALID_CREDENTIALS_ERROR.encode() in response.data


def test_unknown_email_returns_401(client):
    response = _post(client, email="nobody@example.com")
    assert response.status_code == 401
    assert INVALID_CREDENTIALS_ERROR.encode() in response.data


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    """DoD 4. Same email in both requests, so the only possible difference
    would be the message itself."""
    wrong_password = _post(client, email="ghost@example.com",
                           password=VALID["password"])
    unknown_email = _post(client, email="ghost@example.com",
                          password="somethingelse")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.data == unknown_email.data


def test_failed_login_does_not_set_session(client):
    _post(client, password="wrongpassword")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_blank_email_returns_required_message(client):
    response = _post(client, email="")
    assert response.status_code == 401
    assert MISSING_CREDENTIALS_ERROR.encode() in response.data


def test_blank_password_returns_required_message(client):
    response = _post(client, password="")
    assert response.status_code == 401
    assert MISSING_CREDENTIALS_ERROR.encode() in response.data


def test_whitespace_email_returns_required_message(client):
    """Proves .strip() runs before the emptiness check."""
    response = _post(client, email="   ")
    assert response.status_code == 401
    assert MISSING_CREDENTIALS_ERROR.encode() in response.data


def test_missing_fields_returns_required_message(client):
    """Absent keys, not empty ones — this is the `or ""` guard against a 500."""
    response = client.post("/login", data={})
    assert response.status_code == 401
    assert MISSING_CREDENTIALS_ERROR.encode() in response.data


def test_failed_login_keeps_typed_email(client):
    response = _post(client, email="typed@example.com", password="wrongpass")
    assert b'value="typed@example.com"' in response.data


def test_failed_login_never_echoes_the_password(client):
    response = _post(client, password="hunter2secret")
    assert b"hunter2secret" not in response.data


# ------------------------------------------------------------------ #
# Already signed in                                                   #
# ------------------------------------------------------------------ #

def test_get_login_while_authenticated_redirects(client, db_conn):
    with client.session_transaction() as sess:
        sess["user_id"] = _demo_id(db_conn)

    response = client.get("/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_post_login_while_authenticated_redirects(client, db_conn):
    with client.session_transaction() as sess:
        sess["user_id"] = _demo_id(db_conn)

    response = _login(client)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_get_register_while_authenticated_redirects(client, db_conn):
    with client.session_transaction() as sess:
        sess["user_id"] = _demo_id(db_conn)

    response = client.get("/register")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_post_register_while_authenticated_creates_no_user(client, db_conn):
    """The guard must block the write, not just hide the form."""
    with client.session_transaction() as sess:
        sess["user_id"] = _demo_id(db_conn)

    before = db_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    response = client.post("/register", data={
        "name": "Sneaky User",
        "email": "sneaky@example.com",
        "password": "supersecret123",
    })

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert db_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == before


def test_stale_session_id_does_not_crash(client):
    """A signed cookie can outlive its row — that must degrade to logged out,
    never to a 500."""
    with client.session_transaction() as sess:
        sess["user_id"] = 999999

    response = client.get("/")
    assert response.status_code == 200
    assert b"Sign in" in response.data
    assert b"Sign out" not in response.data


# ------------------------------------------------------------------ #
# GET /logout                                                         #
# ------------------------------------------------------------------ #

def test_logout_redirects_to_landing(client):
    _login(client)
    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_logout_clears_session(client):
    _login(client)
    with client.session_transaction() as sess:
        assert "user_id" in sess

    client.get("/logout")

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_flashes_signed_out_message(client):
    """Also guards the clear()-before-flash() ordering: reversed, the message
    would be wiped with the rest of the session."""
    _login(client)
    response = client.get("/logout", follow_redirects=True)
    assert b"You have been signed out." in response.data


def test_logout_restores_logged_out_navbar(client):
    _login(client)
    response = client.get("/logout", follow_redirects=True)
    assert b"Sign in" in response.data
    assert b"Sign out" not in response.data


def test_logout_while_logged_out_redirects_without_error(client):
    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


# ------------------------------------------------------------------ #
# Stub routes are untouched                                           #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("path, expected", [
    ("/profile", "Profile page — coming in Step 4"),
    ("/expenses/add", "Add expense — coming in Step 7"),
    ("/expenses/1/edit", "Edit expense — coming in Step 8"),
    ("/expenses/1/delete", "Delete expense — coming in Step 9"),
])
def test_later_step_stubs_are_unchanged(client, path, expected):
    """DoD 10. Compared as text, not bytes — the stubs contain an em dash."""
    response = client.get(path)
    assert response.status_code == 200
    assert response.get_data(as_text=True) == expected


# ------------------------------------------------------------------ #
# _validate_login — pure unit tests, no client needed                 #
# ------------------------------------------------------------------ #

def test_validate_login_accepts_complete_input():
    assert _validate_login("demo@spendly.com", "demo123") is None


def test_validate_login_rejects_blank_email():
    assert _validate_login("", "demo123") == MISSING_CREDENTIALS_ERROR


def test_validate_login_rejects_blank_password():
    assert _validate_login("demo@spendly.com", "") == MISSING_CREDENTIALS_ERROR


def test_validate_login_does_not_strip_the_password():
    """Deliberate divergence from _validate_registration: the password is never
    stripped, so an all-spaces one passes here and fails the hash check."""
    assert _validate_login("demo@spendly.com", "   ") is None


# ------------------------------------------------------------------ #
# login_required — defined now, first applied in Step 4               #
# ------------------------------------------------------------------ #

def test_login_required_redirects_anonymous_users(app):
    @login_required
    def protected():
        return "secret"

    with app.test_request_context("/profile"):
        response = protected()
        assert response.status_code == 302
        assert response.headers["Location"] == url_for("login")


def test_login_required_preserves_the_view_name(app):
    """Without functools.wraps every protected route would register as the
    endpoint 'wrapped' and the second one would raise at import."""
    @login_required
    def profile():
        return "secret"

    assert profile.__name__ == "profile"


def test_login_required_allows_signed_in_users(app, db_conn):
    @login_required
    def protected():
        return "secret"

    with app.test_request_context("/profile"):
        from flask import session
        session["user_id"] = _demo_id(db_conn)
        assert protected() == "secret"
