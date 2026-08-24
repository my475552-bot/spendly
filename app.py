import sqlite3

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from database.db import (create_user, get_db, get_user_by_email, init_db,
                         seed_db)

app = Flask(__name__)

# Create tables and seed demo data once at startup.
# Module level (not inside __main__) so it also runs under `flask run`
# and pytest.
with app.app_context():
    init_db()
    seed_db()


DUPLICATE_EMAIL_ERROR = "An account with that email already exists."


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

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


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
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


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


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
