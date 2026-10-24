# Changelog

## v2 - review fixes

### Data safety
- Students and courses with enrollments can no longer be deleted (FK `RESTRICT` instead of `CASCADE`); deletion is admin-only and confirmed.
- `CHECK` constraints: marks 0-100, fee >= 0, failed_attempts >= 0. Per-component maxima (default 20/20/60) enforced by the app.
- Grade saving is one atomic `INSERT ... ON DUPLICATE KEY UPDATE` (no check-then-insert race). Dropped enrollments cannot be graded.
- Editing a course that has no instructor no longer silently assigns the first instructor; "None" is a real choice in the Add and Update forms.
- Instructor phone can be edited (and is validated).

### Errors and reliability
- `run_query` raises `DatabaseError` instead of returning `[]`; every page shows one friendly message when the database is down. Dashboard crash on empty/down database fixed.
- Login handles database errors; log messages no longer mislabel query errors as connection failures.
- One shared rotating log handler (previously one per module on the same file). Thread-safe pool creation.
- Success messages survive `st.rerun()` (flash messages); forms are cleared only after a successful save.

### Security
- Same message and same timing for unknown user / wrong password / locked account (no username enumeration).
- Atomic failed-attempt counter in SQL, lock times compared on the database clock, fresh counter after a lock expires.
- Roles are enforced (admin-only deletes, user management, audit log) and re-read from the database on every page load; deactivated users are logged out immediately.
- No personal data in logs: query parameters are never logged, and quoted values in MySQL error text (e.g. `Duplicate entry 'x@y.com'`) are redacted.
- CSV exports neutralise spreadsheet formulas. Passwords: 10+ chars, letter + digit, 72-byte bcrypt limit enforced (no silent truncation).
- Tracebacks hidden from users (`.streamlit/config.toml`); README grants the app account only `SELECT, INSERT, UPDATE, DELETE`.

### Features
- Account page: change own password; admins create users, change roles, activate/deactivate, unlock, reset passwords; audit log viewer.
- Audit trail table (no personal data stored). `updated_at` columns on all tables.
- Search by full name ("John Smith"), with `%` and `_` treated literally. Status filters. Student enrollment date editable.
- Grade percentage and letter grade in the grade table and BR-03 report; BR-03 limited to the top 100.

### Performance and code quality
- Server-side pagination (`LIMIT/OFFSET`) instead of loading every row; cached lookups/reports (cleared on every write); one dashboard query instead of four.
- Shared SQL in `queries.py`; hashing moved to `security.py` (the CLI no longer imports Streamlit); `st.set_page_config` on every page; non-deprecated `width="stretch"`.
- Form widgets keyed by record ID so unsaved text cannot carry over to another record.
- 73 automated tests (unit, database, authentication, and every page driven against a real MySQL).
- README corrected (bcrypt, not passlib).
