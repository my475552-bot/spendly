# Spec: Registration

## Overview

Step 2 turns the existing `/register` page from a static form into a working
sign-up flow. Right now `register.html` renders a complete POST form, but
`app.py` only accepts GET, so submitting it returns `405 Method Not Allowed`.
This step adds POST handling: validate the submitted name, email and password,
reject duplicates and malformed input, hash the password with werkzeug, insert
the user through a new helper in `database/db.py`, and redirect to `/login` on
success. It is the first step that writes user data at runtime, so it
establishes the validation and error-display conventions the rest of the auth
flow (Step 3 login/logout, Step 4 profile) will reuse.

Sessions are deliberately **out of scope**. A successful registration does not
log the user in — it redirects to the login page. `session`, `secret_key` and
`flash()` all arrive in Step 3.

## Depends on

- **Step 1 — Database setup** (complete). Requires `get_db()`, `init_db()` and
  the `users` table (`id`, `name`, `email UNIQUE`, `password_hash`,
  `created_at`) from `database/db.py`.
- The existing `GET /register` route and `templates/register.html`, which
  already renders `{% if error %}<div class="auth-error">{{ error }}</div>`
  and posts fields named `name`, `email`, `password`.

## Routes

- `POST /register` — accepts the sign-up form, validates it, creates the user,
  redirects to `GET /login` on success; re-renders `register.html` with an
  `error` message and a 400 status on failure — **public**
- `GET /register` — unchanged, still renders the empty form — **public**

Implemented by widening the existing route decorator to
`@app.route("/register", methods=["GET", "POST"])`. No other route changes.

## Database changes

**No database changes.** The `users` table created in Step 1 already has every
column this feature needs, including the `UNIQUE` constraint on `email` that
backs duplicate detection. `SCHEMA_SQL` in `database/db.py` must not be edited.

Two new **query helpers** are added to `database/db.py` (functions, not schema):

- `get_user_by_email(email)` — returns a `sqlite3.Row` or `None`
- `create_user(name, email, password_hash)` — inserts and returns the new
  `lastrowid`; raises `sqlite3.IntegrityError` if the email is taken

## Templates

- **Create:** none.
- **Modify:**
  - `templates/register.html` — replace the hardcoded `action="/register"`
    with `action="{{ url_for('register') }}"` (CLAUDE.md forbids hardcoded
    URLs). Add `value="{{ name or '' }}"` to the name input and
    `value="{{ email or '' }}"` to the email input so a rejected submission
    keeps what the user typed. Never repopulate the password field.

## Files to change

- `app.py` — add `request`, `redirect`, `url_for` to the Flask import; add
  `create_user`, `get_user_by_email` to the `database.db` import; widen the
  `/register` route to accept POST and add the handler body.
- `database/db.py` — add `get_user_by_email()` and `create_user()`, and make
  `DB_PATH` overridable (see *Files to create*). `check_password_hash` is
  **not** needed here — that belongs to Step 3.
- `templates/register.html` — `url_for()` fix and sticky field values.
- `CLAUDE.md` — mark `GET /register` / `POST /register` as implemented in the
  route table, and delete the now-stale warning line
  "`database/db.py` is currently empty" (Step 1 implemented it).

## Files to create

- `tests/__init__.py` — empty, so `tests/` is importable.
- `tests/conftest.py` — pytest fixtures: a temporary DB path, an `app` fixture
  and a `client` fixture.
- `tests/test_registration.py` — the test suite for this feature.

**Testing blocker that must be solved in this step:** `DB_PATH` in
`database/db.py:23` is a module-level constant resolved at import time, and
`app.py:10-12` calls `init_db()` / `seed_db()` at import. Without an override,
`pytest` writes into the real `expense_tracker.db`. Fix it the minimal way:
read the path from an environment variable with the current value as the
default —

```python
DB_PATH = os.environ.get("SPENDLY_DB", os.path.join(BASE_DIR, "expense_tracker.db"))
```

— and have `conftest.py` set `SPENDLY_DB` to a `tmp_path` file *before*
importing `app`. Do not add a `db_path` parameter to `get_db()`; the env var is
smaller and touches no call sites.

## New dependencies

**No new dependencies.** `flask==3.1.3`, `werkzeug==3.1.6`, `pytest==8.3.5` and
`pytest-flask==1.3.0` are already pinned in `requirements.txt`. Do not add to
it.

## Validation rules

Validate in this order and return the **first** failure only:

| Condition | Error message |
|---|---|
| any of name / email / password missing or blank after `.strip()` | `All fields are required.` |
| name shorter than 2 chars | `Please enter your full name.` |
| email has no `@` or no `.` after the `@` | `Please enter a valid email address.` |
| password shorter than 8 chars | `Password must be at least 8 characters.` |
| email already in `users` | `An account with that email already exists.` |

Normalise before storing: `name.strip()`, `email.strip().lower()`. Never strip
or alter the password.

## Rules for implementation

- **No SQLAlchemy or any ORM** — `sqlite3` through `get_db()` only.
- **Parameterised queries only** — `?` placeholders, never f-strings in SQL.
- **Passwords hashed with werkzeug** — `generate_password_hash()` from
  `werkzeug.security`. The plaintext password must never be written to the DB,
  logged, or echoed back into the template.
- **Use CSS variables — never hardcode hex values.** No new CSS is expected;
  `.auth-error`, `.form-group`, `.form-input` and `.btn-submit` already exist in
  `static/css/style.css`.
- **All templates extend `base.html`** — `register.html` already does.
- **No DB logic in route functions** — every `SELECT`/`INSERT` lives in
  `database/db.py`. The route calls helpers and nothing else.
- **No `url_for()` violations** — the form `action` must use `url_for`.
- **No sessions, no `flash()`, no `secret_key`** in this step. Errors are passed
  to the template as the `error` variable, matching the existing convention in
  `register.html` and `login.html`.
- Close every connection in a `try/finally`, matching the pattern already used
  by `init_db()` and `seed_db()`.
- Duplicate email must be caught **both** ways: check with
  `get_user_by_email()` first, and still wrap the insert in a
  `try/except sqlite3.IntegrityError` to cover the race.
- Keep the app on **port 5001**.

## Definition of done

Run `python app.py` and visit `http://localhost:5001/register`:

1. Submitting a valid new name / email / password lands on `/login`
   (HTTP 302 → 200), and no error is shown.
2. `sqlite3 expense_tracker.db "SELECT name, email, password_hash FROM users"`
   shows the new row; `email` is lowercased and `password_hash` starts with
   `scrypt:` or `pbkdf2:` — the plaintext password appears nowhere.
3. Submitting the same email a second time re-renders the register page with
   "An account with that email already exists." and adds no second row.
4. Submitting `demo@spendly.com` (the seeded user) is rejected the same way.
5. Submitting with an empty name, a `notanemail` email, or a 5-character
   password each re-renders the page with the matching message from the
   validation table, and each failed submission keeps the typed name and email
   in the inputs while the password box is empty.
6. `GET /register` still returns 200 with a blank form and no error box.
7. View source on `/register`: the form's `action` is the `url_for`-generated
   `/register`, not a hardcoded string.
8. `pytest` passes with the new `tests/test_registration.py` covering: GET 200,
   successful POST redirects to `/login`, user row created with a hashed
   password, duplicate email rejected, and each validation rule.
9. `pytest` leaves the real `expense_tracker.db` unmodified — check its row
   count before and after.
10. `grep -rn "f\"SELECT\|f'SELECT\|f\"INSERT\|f'INSERT" database/ app.py`
    returns nothing.
