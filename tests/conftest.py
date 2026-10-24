"""
Test setup. Unit tests need no database. Integration tests (test_integration.py, test_pages.py)
need a MySQL server; they use a throw-away database called `lms_pytest` and are skipped
automatically when no server is reachable.

Configure with env vars:  TEST_DB_HOST / TEST_DB_PORT / TEST_DB_USER / TEST_DB_PASSWORD
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set BEFORE any project module imports config.
os.environ["DB_HOST"] = os.getenv("TEST_DB_HOST", "127.0.0.1")
os.environ["DB_PORT"] = os.getenv("TEST_DB_PORT", "3306")
os.environ["DB_USER"] = os.getenv("TEST_DB_USER", "lms_test")
os.environ["DB_PASSWORD"] = os.getenv("TEST_DB_PASSWORD", "TestPass#123")
os.environ["DB_NAME"] = "lms_pytest"
os.environ["APP_ENV"] = "production"
os.environ["LOG_DIR"] = tempfile.mkdtemp(prefix="lms_test_logs_")
os.environ["MAX_LOGIN_ATTEMPTS"] = "3"
os.environ["CACHE_TTL_SECONDS"] = "30"

import mysql.connector  # noqa: E402
import pytest  # noqa: E402

TEST_DB = "lms_pytest"
TABLES = ["audit_log", "grades", "enrollments", "courses", "instructors", "students", "users"]


def _admin_connection(database=None):
    return mysql.connector.connect(
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], database=database,
    )


@pytest.fixture(scope="session")
def database():
    """Create a fresh test database from sql/schema.sql (once per test session)."""
    try:
        conn = _admin_connection()
    except mysql.connector.Error as e:
        pytest.skip(f"MySQL not reachable for integration tests: {e}")
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    schema = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8").replace("lms_database", TEST_DB)
    for _ in cur.execute(schema, multi=True):
        pass
    conn.commit()
    cur.close()
    conn.close()
    yield TEST_DB
    conn = _admin_connection()
    conn.cursor().execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture()
def db(database):
    """Empty tables + two known users (admin / staff) before every test."""
    import streamlit as st
    from security import hash_password

    conn = _admin_connection(TEST_DB)
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in TABLES:
        cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    pw_hash = hash_password("CorrectHorse9")
    cur.execute("INSERT INTO users (username, password_hash, role) VALUES ('admin1', %s, 'admin'), "
                "('staff1', %s, 'staff')", (pw_hash, pw_hash))
    conn.commit()
    st.cache_data.clear()
    yield conn
    conn.close()


@pytest.fixture()
def sql(db):
    """Tiny helper: sql('SELECT ...', params) -> list of dict rows (or affected rowcount)."""
    def run(query, params=()):
        cur = db.cursor(dictionary=True)
        cur.execute(query, params)
        if cur.with_rows:
            rows = cur.fetchall()
        else:
            rows = cur.rowcount
        db.commit()
        cur.close()
        return rows
    return run
