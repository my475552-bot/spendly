import functools
import os
import sqlite3

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (create_user, get_db, get_user_by_email,
                         get_user_by_id, init_db, seed_db)

app = Flask(__name__)

# Signs the session cookie. Set before anything touches the app, so a future
# session or flash inside the startup context below cannot fail with
# "The session is unavailable because no secret key was set".
#
# Changing this value invalidates every cookie signed with the old one, which
# is the only way to force everybody to sign in again. Rotate it whenever user
# ids change meaning — a cookie holds a bare user_id, so a renumbered table
# would otherwise hand one person's session to another account.
# Rotated 2026-08-24 after users 4/5 were renumbered to 3/4.
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY",
                                "dev-only-change-me-r2-20260824")

# Create tables and seed demo data once at startup.
# Module level (not inside __main__) so it also runs under `flask run`
# and pytest.
with app.app_context():
    init_db()
    seed_db()


DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
# One constant, two call sites: a wrong email and a wrong password must be
# indistinguishable, and sharing the string is what keeps them that way.
INVALID_CREDENTIALS_ERROR = "Incorrect email or password."
MISSING_CREDENTIALS_ERROR = "Please enter your email and password."


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def current_user():
    """Return the signed-in user's row, or None if nobody is signed in.

    Cached on ``g`` — request-scoped, so it cannot leak between requests or
    between tests. ``base.html`` renders the navbar on every page and
    ``login_required`` calls this too, and ``get_db()`` opens a fresh
    connection every time, so an uncached version would query twice per page.
    Do not move this cache onto the app or a module global.

    A session id with no matching row (deleted user, or a cookie that outlived
    the database) resolves to None, exactly like no session at all.
    """
    if "current_user" not in g:
        user_id = session.get("user_id")
        g.current_user = get_user_by_id(user_id) if user_id else None
    return g.current_user


def _forget_current_user():
    """Drop the cached user after the session changes.

    Anything that writes to ``session`` must call this, or the rest of the
    context keeps serving the pre-change answer. ``g`` is bound to the app
    context, not the request, so a single app context spanning two requests
    (pytest-flask pushes exactly that) would otherwise render a stale navbar.
    """
    g.pop("current_user", None)


@app.context_processor
def inject_current_user():
    """Expose ``current_user`` to every template without a route passing it."""
    return {"current_user": current_user()}


def login_required(view):
    """Redirect anonymous visitors to the sign-in page.

    Defined for Step 4 onwards; no route uses it yet. ``functools.wraps`` is
    required — Flask keys its URL map on the view's ``__name__``, so without it
    every protected route would register as the endpoint ``wrapped``.
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def _validate_registration(name, email, password):
    """Return the first registration error message, or None if the input is ok.

    ``name`` and ``email`` are expected already normalised; ``password`` is the
    raw submitted value and is never modified here. The duplicate-email check
    lives in the route instead — it needs the database.
    """
    if not name or not email or not password.strip():
        return "All fields are required."

    if len(name) < 2:
        return "Please enter your full name."

    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        return "Please enter a valid email address."

    if len(password) < 8:
        return "Password must be at least 8 characters."

    return None


def _validate_login(email, password):
    """Return the first credential-format error, or None if the input is ok.

    ``email`` is expected already normalised; ``password`` is the raw submitted
    value. Unlike ``_validate_registration`` this never calls ``.strip()`` on
    the password — an all-spaces password is deliberately allowed through here
    and rejected by the hash check instead. The account lookup and the hash
    check live in the route; they need the database.
    """
    if not email or not password:
        return MISSING_CREDENTIALS_ERROR

    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Signing up while signed in is never intended — same guard as login().
    if current_user() is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        error = _validate_registration(name, email, password)

        if error is None and get_user_by_email(email) is not None:
            error = DUPLICATE_EMAIL_ERROR

        if error is None:
            try:
                create_user(name, email, generate_password_hash(password))
            except sqlite3.IntegrityError:
                # Another request registered this email between the check
                # above and the insert.
                error = DUPLICATE_EMAIL_ERROR
            else:
                return redirect(url_for("login"))

        return render_template("register.html", error=error,
                               name=name, email=email), 400

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        error = _validate_login(email, password)

        if error is None:
            user = get_user_by_email(email)
            # One branch, one message: an unknown email and a bad password
            # must be indistinguishable to the caller.
            if user is None or not check_password_hash(
                    user["password_hash"], password):
                error = INVALID_CREDENTIALS_ERROR

        if error is None:
            # clear() first — it drops stale keys, and clearing afterwards
            # would wipe the id we just set.
            session.clear()
            session["user_id"] = user["id"]
            _forget_current_user()
            flash(f"Welcome back, {user['name']}.", "success")
            return redirect(url_for("landing"))

        return render_template("login.html", error=error, email=email), 401

    return render_template("login.html")


@app.route("/logout")
def logout():
    # clear() before flash(): the flash queue lives in the session, so the
    # reverse order would silently swallow the message.
    session.clear()
    _forget_current_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
