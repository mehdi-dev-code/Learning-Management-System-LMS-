"""
db.py
Pooled MySQL access layer.

Design rules:
  * Every function RAISES DatabaseError on failure. (The old run_query()
    returned [] on error, so a dead database looked like "no records".)
  * DatabaseError messages are always safe to show to end users; the full
    driver error goes to the log file.
  * Query parameters are never logged (they contain personal data).
"""

import re
import threading
from contextlib import contextmanager

from mysql.connector import Error, pooling

from config import config
from logger import get_logger

log = get_logger(__name__)


class DatabaseError(Exception):
    """A database operation failed. str(e) is safe to display to users."""


_pool: pooling.MySQLConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pooling.MySQLConnectionPool:
    """Create the pool once, even when several Streamlit threads ask at the same time."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = pooling.MySQLConnectionPool(
                        pool_name=config.DB_POOL_NAME,
                        pool_size=config.DB_POOL_SIZE,
                        **config.db_config,
                    )
                except Error as e:
                    log.error("Could not create MySQL connection pool: %s", e)
                    raise DatabaseError("Could not connect to the database.") from e
                log.info("Initialized MySQL connection pool (size=%s)", config.DB_POOL_SIZE)
    return _pool


@contextmanager
def get_connection():
    """Yield a pooled connection; always returned to the pool on exit.

    Only the *acquire* step is translated to "could not connect". Errors that
    happen while running a query are handled by the caller, so they are no
    longer mislabelled as connection failures in the log.
    """
    try:
        conn = _get_pool().get_connection()
    except DatabaseError:
        raise
    except Error as e:
        log.error("Failed to obtain DB connection: %s", e)
        raise DatabaseError("Could not connect to the database.") from e
    try:
        yield conn
    finally:
        conn.close()  # returns the connection to the pool, doesn't destroy it


def _short(query: str) -> str:
    return " ".join(query.split())[:200]


_QUOTED = re.compile(r"\b(column|key|table|constraint)(\s+)'([^']*)'|'[^']*'")


def _safe_error_text(e: Error) -> str:
    """Error text for the log with data values removed.

    MySQL embeds the offending VALUE in some messages (e.g. "Duplicate entry 'ali@x.com' for
    key ..."), which would put personal data into the log file. Quoted names that follow
    'column' / 'key' / 'table' / 'constraint' are kept; every other quoted value is hidden.
    """
    def _replace(match):
        if match.group(1):
            return match.group(0)
        return "'<hidden>'"
    return _QUOTED.sub(_replace, str(e))


def run_query(query: str, params: tuple | list = ()) -> list[dict]:
    """Run a SELECT and return rows as a list of dicts. Raises DatabaseError on failure."""
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        except Error as e:
            log.error("Query failed (errno=%s): %s | %s", e.errno, _safe_error_text(e), _short(query))
            raise DatabaseError(_friendly_message(e)) from e
        finally:
            cursor.close()


def run_one(query: str, params: tuple | list = ()) -> dict | None:
    """Run a SELECT and return the first row, or None when there is no row."""
    rows = run_query(query, params)
    return rows[0] if rows else None


def run_action(query: str, params: tuple | list = ()) -> int:
    """Run INSERT/UPDATE/DELETE. Returns the number of affected rows."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, tuple(params))
            conn.commit()
            return cursor.rowcount
        except Error as e:
            conn.rollback()
            log.error("Action failed (errno=%s): %s | %s", e.errno, _safe_error_text(e), _short(query))
            raise DatabaseError(_friendly_message(e)) from e
        finally:
            cursor.close()


def run_action_get_id(query: str, params: tuple | list = ()) -> int:
    """Run an INSERT and return the generated primary key."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, tuple(params))
            conn.commit()
            return cursor.lastrowid
        except Error as e:
            conn.rollback()
            log.error("Insert failed (errno=%s): %s | %s", e.errno, _safe_error_text(e), _short(query))
            raise DatabaseError(_friendly_message(e)) from e
        finally:
            cursor.close()


def run_transaction(statements: list[tuple[str, tuple | list]]) -> None:
    """Run several statements as ONE transaction: all succeed or none are applied."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            for query, params in statements:
                cursor.execute(query, tuple(params))
            conn.commit()
        except Error as e:
            conn.rollback()
            log.error("Transaction failed (errno=%s): %s", e.errno, _safe_error_text(e))
            raise DatabaseError(_friendly_message(e)) from e
        finally:
            cursor.close()


# MySQL error numbers -> messages that are safe to show to users.
_ERRNO_MESSAGES = {
    1062: "A record with that value already exists.",
    1048: "A required field was left empty.",
    1406: "One of the values is too long.",
    1264: "One of the numbers is out of the allowed range.",
    3819: "One of the values is outside the allowed range.",  # CHECK constraint (MySQL)
    4025: "One of the values is outside the allowed range.",  # CHECK constraint (MariaDB)
    1451: "This record is still used by other records (for example enrollments). "
          "Set its status to Inactive instead of deleting it.",
    1452: "A selected student, course or instructor no longer exists. Please refresh and try again.",
}


def _friendly_message(e: Error) -> str:
    """Translate MySQL errors into messages safe to show end users."""
    msg = _ERRNO_MESSAGES.get(getattr(e, "errno", None))
    if msg:
        return msg
    text = str(e).lower()
    if "duplicate entry" in text:
        return _ERRNO_MESSAGES[1062]
    if "foreign key constraint fails" in text:
        return _ERRNO_MESSAGES[1451]
    return "The operation could not be completed. Please try again or contact an administrator."


def test_connection() -> bool:
    """Quick sanity check - run `python db.py` to test the connection."""
    try:
        with get_connection() as conn:
            print(f"Connected to MySQL successfully. Server version: {conn.get_server_info()}")
            return True
    except DatabaseError as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
