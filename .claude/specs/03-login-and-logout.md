# Spec: Login and Logout

## Overview

Step 3 makes Spendly aware of *who* is using it. Step 2 can create a user but
cannot recognise one: `templates/login.html` already renders a complete POST
form, yet `app.py:86` only accepts GET, so submitting it returns
`405 Method Not Allowed`, and `/logout` is still a stub returning the raw
string `"Logout — coming in Step 3"`. This step adds POST handling to `/login`
(look the user up by email, verify the password with
`werkzeug.security.check_password_hash`, and store their id in the Flask
session), implements `/logout` (clear the session and redirect home), and
introduces the three pieces of app-wide plumbing every later step depends on:
`app.secret_key`, `session`, and `flash()` messages rendered in `base.html`.
It is the first step where the app has a logged-in state, so it also makes the
navbar reflect that state and adds the `login_required` decorator that Steps 4
and 7–9 will hang their protected routes on.

Because `GET /profile` is still a Step 4 stub, a successful login redirects to
the landing page (`GET /`) with a "Welcome back" flash. Step 4 changes that
destination to `/profile`; nothing else about this flow changes.

## Depends on

- **Step 1 — Database setup** (complete). Requires `get_db()` and the `users`
  table with `id`, `name`, `email UNIQUE`, `password_hash`.
- **Step 2 — Registration** (complete). Requires `get_user_by_email()` in
  `database/db.py`, the `generate_password_hash()` convention that put a
  werkzeug hash in `users.password_hash`, and the `error`-variable error
  display already present in `login.html` and `register.html`.
- The existing `tests/conftest.py`, whose `SPENDLY_DB` / `reset_db` machinery
  the new tests reuse unchanged.

## Routes

- `POST /login` — accepts the sign-in form, verifies email + password, stores
  `session["user_id"]`, flashes a welcome message and redirects to `GET /` —
  **public**
- `GET /login` — renders the empty sign-in form; if the visitor is already
  logged in, redirects to `GET /` instead — **public**
- `GET /logout` — clears the session, flashes "You have been signed out." and
  redirects to `GET /` — **logged-in** (a logged-out visitor is simply
  redirected home, no error)
- `GET, POST /register` — behaviour unchanged for anonymous visitors, but a
  signed-in visitor is redirected to `GET /` instead — **public**

`GET /login` is implemented by widening the existing decorator to
`@app.route("/login", methods=["GET", "POST"])`. `GET /logout` replaces the
stub body at `app.py:105-107`. **No other stub route is touched** — `/profile`,
`/expenses/add`, `/expenses/<id>/edit` and `/expenses/<id>/delete` stay exactly
as they are.

**The already-signed-in guard applies to `/login` and `/register` alike, on
both methods.** Put it at the top of each view, before the `request.method`
branch — guarding only the GET would hide the form while still letting a
submitted POST re-authenticate over a live session, or create a second account
from inside one. Neither page has any meaning to someone already signed in.

## Database changes

**No database changes.** The `users` table from Step 1 already stores the
werkzeug hash this feature verifies against; `SCHEMA_SQL` in `database/db.py`
must not be edited. No session table — Flask's signed cookie holds the session.

One new **query helper** is added to `database/db.py` (a function, not schema):

- `get_user_by_id(user_id)` — returns a `sqlite3.Row` or `None`, used to turn
  `session["user_id"]` back into a user for the navbar and for
  `login_required`. Parameterised (`WHERE id = ?`), same `try/finally`
  connection pattern as `get_user_by_email()`.

`get_user_by_email()` is reused as-is for the login lookup.

## Templates

- **Create:** none.
- **Modify:**
  - `templates/login.html` — replace the hardcoded `action="/login"` with
    `action="{{ url_for('login') }}"` (CLAUDE.md forbids hardcoded URLs). Add
    `value="{{ email or '' }}"` to the email input so a rejected sign-in keeps
    the typed address. **Never** repopulate the password field.
  - `templates/base.html` — two changes:
    1. Render flashed messages once, above `{% block content %}`, using
       `get_flashed_messages(with_categories=true)` and a `.flash` /
       `.flash-<category>` markup block. Categories used in this step:
       `success` and `info`.
    2. Make `.nav-links` conditional on `current_user`: logged out shows the
       existing "Sign in" / "Get started" links; logged in shows the user's
       name and a "Sign out" link to `url_for('logout')`. `current_user` comes
       from a `@app.context_processor`, so no route has to pass it.

## Files to change

- `app.py`
  - add the already-signed-in guard to `register()` as well as `login()` — it
    is the only change to the Step 2 route.
  - imports: add `session`, `flash` to the Flask import; add
    `check_password_hash` to the `werkzeug.security` import; add
    `get_user_by_id` to the `database.db` import; add `functools.wraps`.
  - add `app.secret_key`, read from the environment with a dev default:
    `app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")`
    (add `import os`). Sessions do not work without it.
  - add a `current_user()` helper — returns the `sqlite3.Row` for
    `session.get("user_id")`, or `None` — and expose it to every template with
    `@app.context_processor`.
  - add a `login_required` decorator that flashes "Please sign in to continue."
    and redirects to `url_for("login")` when `current_user()` is `None`. It is
    **defined but not applied to any route in this step** — Step 4 is the first
    consumer.
  - widen `/login` to `methods=["GET", "POST"]` and add the handler body.
  - replace the `/logout` stub body with `session.clear()`, a flash and a
    redirect.
- `database/db.py` — add `get_user_by_id()`. Nothing else changes; `DB_PATH`,
  `SCHEMA_SQL`, `seed_db()` and the existing helpers stay untouched.
- `templates/login.html` — `url_for()` fix and sticky email value.
- `templates/base.html` — flash message block and conditional nav.
- `static/css/style.css` — add `.flash`, `.flash-success`, `.flash-info` and a
  `.nav-user` rule for the logged-in navbar, built only from the existing
  `:root` variables (`--accent`, `--accent-light`, `--danger`,
  `--danger-light`, `--border`, `--ink-muted`, `--radius-sm`, …).
- `CLAUDE.md` — in the route table mark `POST /login` and `GET /logout` as
  implemented and drop `GET /logout` from the stub list; leave every other stub
  row alone.

## Files to create

- `tests/test_login.py` — sign-in, session and sign-out coverage (see
  *Definition of done*).

No new conftest work is needed: `tests/conftest.py` already sets `SPENDLY_DB`
at module level before importing `app`, and its `client` fixture is per-test,
so session cookies never bleed between tests.

## New dependencies

**No new dependencies.** `flask==3.1.3`, `werkzeug==3.1.6`, `pytest==8.3.5` and
`pytest-flask==1.3.0` in `requirements.txt` cover everything — `session`,
`flash` and `check_password_hash` all ship with Flask/Werkzeug. Do not add to
`requirements.txt`.

## Validation rules

Check in this order and return the **first** failure only:

| Condition | Error message |
|---|---|
| email or password missing / blank after `.strip()` on the email | `Please enter your email and password.` |
| no user with that email | `Incorrect email or password.` |
| `check_password_hash()` fails | `Incorrect email or password.` |

The wrong-email and wrong-password cases must share one message — never reveal
whether an account exists. Normalise the email with `.strip().lower()` before
the lookup (the `UNIQUE` column and `get_user_by_email()` are both
case-sensitive). Never strip or alter the password. A failed sign-in re-renders
`login.html` with `error` and HTTP **401**.

On success: `session.clear()` first (drops any stale keys), then
`session["user_id"] = user["id"]`, `flash(f"Welcome back, {user['name']}.",
"success")`, `redirect(url_for("landing"))`.

## Rules for implementation

- **No SQLAlchemy or ORMs** — `sqlite3` through `get_db()` only.
- **Parameterised queries only** — `?` placeholders, never f-strings in SQL.
- **Passwords hashed with werkzeug** — verify with `check_password_hash()`
  only. Never compare hashes with `==`, never log or echo the plaintext
  password, never store it in the session.
- **Use CSS variables — never hardcode hex values.** Every new rule in
  `style.css` references `var(--…)` from the existing `:root` block; add a new
  variable there if a colour is genuinely missing.
- **All templates extend `base.html`** — `login.html` already does; the flash
  block lives in `base.html` so no page renders its own.
- **No DB logic in route functions** — the `SELECT` by id goes in
  `database/db.py`; routes call helpers only.
- **No hardcoded URLs** — `url_for()` in every template link and every
  `redirect()`.
- **The session stores only `user_id`** — never the name, email or hash. Read
  the rest through `current_user()` on each request.
- **Do not implement any other stub route.** `/profile` and the expense routes
  remain untouched Step 4 / 7–9 work, and `login_required` is defined but left
  unapplied.
- Close every connection in a `try/finally`, matching `get_user_by_email()`.
- No new pip packages; keep the app on **port 5001**.

## Definition of done

Run `python app.py` and visit `http://localhost:5001/login`:

1. Signing in as the seeded user `demo@spendly.com` / `demo123` redirects to
   `/` (HTTP 302 → 200) and shows a "Welcome back, Demo User." flash.
2. After signing in, the navbar on every page shows the user's name and a
   "Sign out" link instead of "Sign in" / "Get started".
3. `DEMO@SPENDLY.COM` with the correct password signs in exactly the same way
   (email is lowercased before lookup).
4. A wrong password, and an email with no account, each re-render `/login`
   with **"Incorrect email or password."** and HTTP 401 — the two cases are
   indistinguishable in the response body.
5. Submitting an empty email or empty password re-renders with "Please enter
   your email and password."; the typed email is kept in the input and the
   password box is empty on every failed attempt.
6. Visiting `/logout` while signed in redirects to `/`, shows "You have been
   signed out.", and the navbar is back to its logged-out links; hitting
   `/logout` again while logged out still redirects to `/` without an error.
7. After logout, the browser's `session` cookie no longer authenticates —
   reloading `/` shows the logged-out navbar.
8. Visiting `/login` while already signed in redirects to `/` instead of
   showing the form.
8b. Visiting `/register` while already signed in likewise redirects to `/`, and
   **POSTing** the sign-up form from a signed-in session also redirects without
   creating a user — check the row count is unchanged, not just the response.
   Both pages stay fully available to anonymous visitors.
9. View source on `/login`: the form `action` is the `url_for`-generated
   `/login`, not a hardcoded string.
10. `/profile`, `/expenses/add`, `/expenses/<id>/edit` and
    `/expenses/<id>/delete` still return their unchanged Step 4 / 7–9 stub
    strings.
11. `pytest` passes with `tests/test_login.py` covering: the two guard cases in
    item 8b; `GET /login` 200;
    successful POST sets `session["user_id"]` and redirects to `/`; wrong
    password → 401 with the shared message; unknown email → 401 with the same
    message; blank fields → the required-fields message; `GET /logout` clears
    `session`; and `GET /login` while authenticated redirects.
12. `pytest` leaves the real `expense_tracker.db` unmodified — row counts match
    before and after.
13. `grep -rn "f\"SELECT\|f'SELECT\|f\"INSERT\|f'INSERT" database/ app.py`
    returns nothing, and `grep -rn "#[0-9a-fA-F]\{3,6\}" static/css/style.css`
    shows hex values only inside the `:root` block.
