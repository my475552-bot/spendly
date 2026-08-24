"""Tests for Step 2 — registration.

Row counts here are always filtered by email or compared as deltas: every test
starts with the seeded demo user already in the table (see conftest.reset_db),
so absolute counts would be brittle. Ids are never asserted on — the demo user
owns id 1 and DELETE does not reset AUTOINCREMENT.
"""

import os

from werkzeug.security import check_password_hash

from app import _validate_registration
from database import db as db_module

VALID = {
    "name": "Test User",
    "email": "test@example.com",
    "password": "supersecret123",
}


def _post(client, **overrides):
    """POST the valid payload with any field replaced or removed."""
    data = dict(VALID)
    data.update(overrides)
    return client.post("/register", data=data)


def _count_with_email(conn, email):
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE email = ?", (email,)
    ).fetchone()[0]


# ------------------------------------------------------------------ #
# Test isolation                                                      #
# ------------------------------------------------------------------ #

def test_tests_do_not_touch_the_real_database():
    """conftest must have redirected DB_PATH away from the real file."""
    real_db = os.path.join(db_module.BASE_DIR, "expense_tracker.db")
    assert db_module.DB_PATH != real_db
    assert "spendly-test-" in db_module.DB_PATH


def test_reset_db_leaves_only_the_seeded_user(db_conn):
    users = db_conn.execute("SELECT * FROM users").fetchall()
    assert len(users) == 1
    assert users[0]["email"] == "demo@spendly.com"


# ------------------------------------------------------------------ #
# GET /register                                                       #
# ------------------------------------------------------------------ #

def test_get_register_returns_200(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b'name="email"' in response.data


def test_get_register_has_no_error_box(client):
    response = client.get("/register")
    assert b"auth-error" not in response.data


def test_get_register_has_empty_fields(client):
    response = client.get("/register")
    assert b'value=""' in response.data


def test_register_template_has_no_hardcoded_action():
    """DoD 7 is really a code-review item — url_for('register') and a literal
    "/register" render identically, so the only automatable check is on the
    template source.
    """
    template = os.path.join(db_module.BASE_DIR, "templates", "register.html")
    with open(template, encoding="utf-8") as handle:
        source = handle.read()
    assert 'action="/register"' not in source
    assert "url_for('register')" in source


# ------------------------------------------------------------------ #
# Successful registration                                             #
# ------------------------------------------------------------------ #

def test_valid_registration_redirects_to_login(client):
    response = _post(client)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_valid_registration_lands_on_login_page(client):
    response = client.post("/register", data=VALID, follow_redirects=True)
    assert response.status_code == 200
    assert b"Sign in" in response.data


def test_valid_registration_creates_user_row(client, db_conn):
    _post(client)
    row = db_conn.execute(
        "SELECT * FROM users WHERE email = ?", (VALID["email"],)
    ).fetchone()
    assert row is not None
    assert row["name"] == "Test User"


def test_name_is_stripped(client, db_conn):
    _post(client, name="  Test User  ")
    row = db_conn.execute(
        "SELECT * FROM users WHERE email = ?", (VALID["email"],)
    ).fetchone()
    assert row["name"] == "Test User"


def test_email_is_lowercased_and_stripped(client):
    _post(client, email="  Test@Example.COM  ")
    assert db_module.get_user_by_email("test@example.com") is not None


def test_password_is_hashed_not_plaintext(client, db_conn):
    _post(client)
    row = db_conn.execute(
        "SELECT * FROM users WHERE email = ?", (VALID["email"],)
    ).fetchone()
    assert row["password_hash"] != VALID["password"]
    assert VALID["password"] not in row["password_hash"]
    assert check_password_hash(row["password_hash"], VALID["password"])


# ------------------------------------------------------------------ #
# Duplicate emails                                                    #
# ------------------------------------------------------------------ #

def test_duplicate_email_rejected(client):
    _post(client)
    response = _post(client)
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data


def test_duplicate_email_creates_no_second_row(client, db_conn):
    _post(client)
    _post(client)
    assert _count_with_email(db_conn, VALID["email"]) == 1


def test_seeded_demo_email_rejected(client):
    response = _post(client, email="demo@spendly.com")
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data


def test_duplicate_check_is_case_insensitive(client, db_conn):
    """Without lowercasing before the lookup this would create a shadow
    account — SQLite's UNIQUE constraint is case-sensitive.
    """
    response = _post(client, email="DEMO@SPENDLY.COM")
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data
    assert _count_with_email(db_conn, "demo@spendly.com") == 1


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #
# These cases are unreachable through a browser — the form's `required` and
# `type="email"` attributes block them client-side — so the test client is the
# only way to exercise the server-side rules.

def test_missing_name_rejected(client):
    response = _post(client, name="")
    assert response.status_code == 400
    assert b"All fields are required." in response.data


def test_whitespace_only_name_rejected(client):
    response = _post(client, name="   ")
    assert response.status_code == 400
    assert b"All fields are required." in response.data


def test_whitespace_only_password_rejected(client):
    response = _post(client, password="        ")
    assert response.status_code == 400
    assert b"All fields are required." in response.data


def test_absent_fields_rejected(client):
    """A POST with no fields at all must be a 400, not a 500."""
    response = client.post("/register", data={})
    assert response.status_code == 400
    assert b"All fields are required." in response.data


def test_short_name_rejected(client):
    response = _post(client, name="A")
    assert response.status_code == 400
    assert b"Please enter your full name." in response.data


def test_invalid_email_rejected(client):
    response = _post(client, email="notanemail")
    assert response.status_code == 400
    assert b"Please enter a valid email address." in response.data


def test_email_without_dot_in_domain_rejected(client):
    response = _post(client, email="a@b")
    assert response.status_code == 400
    assert b"Please enter a valid email address." in response.data


def test_short_password_rejected(client):
    response = _post(client, password="abc12")
    assert response.status_code == 400
    assert b"Password must be at least 8 characters." in response.data


def test_validation_reports_first_failure_only(client):
    response = _post(client, name="", password="abc")
    assert b"All fields are required." in response.data
    assert b"Password must be at least 8 characters." not in response.data


def test_failed_registration_creates_no_row(client, db_conn):
    _post(client, password="abc12")
    assert _count_with_email(db_conn, VALID["email"]) == 0


# ------------------------------------------------------------------ #
# Re-rendered form                                                    #
# ------------------------------------------------------------------ #

def test_rejection_keeps_name_and_email(client):
    response = _post(client, password="abc12")
    assert b'value="Test User"' in response.data
    assert b'value="test@example.com"' in response.data


def test_rejection_never_echoes_password(client):
    response = _post(client, password="abc12")
    assert b"abc12" not in response.data


# ------------------------------------------------------------------ #
# _validate_registration — pure unit tests, no client needed          #
# ------------------------------------------------------------------ #

def test_validate_accepts_good_input():
    assert _validate_registration("Test User", "test@example.com",
                                  "supersecret123") is None


def test_validate_rejects_blank_fields():
    assert _validate_registration("", "test@example.com",
                                  "supersecret123") == \
        "All fields are required."


def test_validate_rejects_short_name():
    assert _validate_registration("A", "test@example.com",
                                  "supersecret123") == \
        "Please enter your full name."


def test_validate_rejects_email_without_local_part():
    assert _validate_registration("Test User", "@example.com",
                                  "supersecret123") == \
        "Please enter a valid email address."


def test_validate_rejects_email_without_at_sign():
    assert _validate_registration("Test User", "no.at.sign",
                                  "supersecret123") == \
        "Please enter a valid email address."


def test_validate_rejects_short_password():
    assert _validate_registration("Test User", "test@example.com",
                                  "abc12") == \
        "Password must be at least 8 characters."


def test_validate_does_not_strip_password():
    """A password of exactly 8 chars with padding is long enough as typed."""
    assert _validate_registration("Test User", "test@example.com",
                                  "  abc123  ") is None
