# Learning Management System (LMS)

A web app for managing students, instructors, courses, enrollments and grades, with role-based access, an audit trail and CSV reports. Built with **Python, Streamlit and MySQL**.

<!-- Add 3-4 screenshots here: login, dashboard, grades table, reports.
![Dashboard](docs/dashboard.png) -->

## Features

- **Records management:** create, edit, search and filter students, instructors and courses. Paging is done in SQL, so large tables stay fast.
- **Enrollments and grades:** enroll active students in active courses (duplicates are refused). Grades are saved per enrollment as assignments, quizzes and a final exam; the total, percentage and letter grade (A-F) are calculated automatically.
- **Reports:** six management reports (highest-enrollment courses, courses per instructor, top students, active student count, enrollment status breakdown, courses with no students) with CSV export.
- **Role-based access:** `admin` (everything, including permanent deletes, user management and the audit log) and `staff` (create/edit records, enroll, grade, run reports).
- **Audit trail:** every create, update, delete, grade save and password change is recorded (who, what, which record, when). Names, emails and phone numbers are never stored in it.
- **Safe deletes:** students and courses that have enrollments cannot be deleted. They are set to *Inactive* so history and grades stay intact.

## Security

- Passwords hashed with **bcrypt**; new passwords need 10+ characters with a letter and a digit.
- Account lockout after repeated failed logins. Unknown user, wrong password and locked account show the same message (no username enumeration).
- Roles are re-read from the database on every page load, and deactivating a user logs them out immediately.
- No personal data in logs: query parameters are never logged and quoted values in database errors are redacted.
- CSV exports neutralise spreadsheet formulas.
- Tracebacks are hidden from users. The app's MySQL account needs only `SELECT, INSERT, UPDATE, DELETE`.

## Tech stack

| Layer | Tools |
|---|---|
| UI | Streamlit (multi-page app) |
| Database | MySQL 8.0.16+ (foreign keys and `CHECK` constraints), connection pooling |
| Data handling | pandas |
| Auth | bcrypt |
| Config | python-dotenv |
| Tests | pytest, Streamlit's `streamlit.testing` |

## Database

Seven tables: `users`, `students`, `instructors`, `courses`, `enrollments`, `grades`, `audit_log`. The full schema is in [`sql/schema.sql`](sql/schema.sql); upgrade scripts are in [`sql/migrations/`](sql/migrations/).

## Quick start

Requires **Python 3.10+** and **MySQL 8.0.16+**.

```bash
# 1. Python environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Create the database and tables (admin MySQL account)
mysql -u root -p < sql/schema.sql

# 3. Create a least-privilege account for the app
mysql -u root -p -e "
  CREATE USER 'lms_app'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
  GRANT SELECT, INSERT, UPDATE, DELETE ON lms_database.* TO 'lms_app'@'localhost';"

# 4. Configure
cp .env.example .env                 # then edit DB_USER / DB_PASSWORD

# 5. Create the first administrator (password is typed hidden)
python scripts/create_user.py

# 6. Run
streamlit run app.py
```

All settings (page size, session timeout, lockout policy, grading scheme) are documented in [`.env.example`](.env.example). The default grading scheme is assignments /20 + quizzes /20 + final exam /60.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/test_units.py     # unit tests, no database needed
pytest                         # everything (needs a MySQL server)
```

The integration and page tests drive the real Streamlit pages against a MySQL database named `lms_pytest`. **They drop and recreate that database**, so point them at a throw-away server or account:

```bash
export TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=3306 \
       TEST_DB_USER=<user with CREATE/DROP rights> TEST_DB_PASSWORD=<password>
```

They are skipped automatically when no MySQL server is reachable.

## Project layout

```
app.py                  login + home
auth.py                 login, lockout, session, roles, password change
security.py             bcrypt hashing + password policy
db.py                   pooled MySQL access
audit.py                audit trail writer
config.py / logger.py   settings / rotating log
queries.py              SQL shared by several pages
pages/                  Dashboard, Students, Instructors, Courses,
                        Enrollments, Grades, Reports, Account
utils/                  UI helpers, validators, grading, CSV export
scripts/create_user.py  create a user or reset a password from the CLI
sql/                    schema and migrations
tests/                  unit, integration and page tests
```

## Known limits

No Docker setup, no migration framework (migrations are plain SQL files), no e-mail password reset, no two-factor authentication, no per-course permissions, and the cache is not shared between several app processes. See [`CHANGELOG.md`](CHANGELOG.md) for what changed in v2.

## Author

**Mehdi Ali** - [GitHub](https://github.com/mehdi-dev-code) - [LinkedIn](https://linkedin.com/in/mehdi-ali-a33881296)
"# Learning-Management-System-LMS-" 
