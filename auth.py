"""
auth.py
Authentication, session handling and role checks.

  * bcrypt password hashing (see security.py)
  * lockout after repeated failures - counted atomically in SQL, and all lock
    times are compared with the DATABASE clock, so app/DB timezone differences
    cannot cause trouble
  * identical response for "unknown user", "wrong password" and "locked"
    (no username enumeration, no timing difference)
  * every page load re-checks that the account is still active and re-reads its
    role, so deactivating or demoting a user takes effect immediately
"""

from datetime import datetime, timedelta

import streamlit as st

from config import config
from db import DatabaseError, run_action, run_one
from logger import get_logger
from security import burn_time, hash_password, validate_password_strength, verify_password

log = get_logger(__name__)

GENERIC_LOGIN_ERROR = "Invalid username or password, or the account is temporarily locked."
UNAVAILABLE_MESSAGE = "The service is temporarily unavailable. Please try again shortly."


# ---------------------------------------------------------------- login ----
def _get_user(username: str) -> dict | None:
    return run_one(
        """
        SELECT user_id, username, password_hash, role, failed_attempts,
               (locked_until IS NOT NULL AND locked_until > NOW())  AS is_locked,
               (locked_until IS NOT NULL AND locked_until <= NOW()) AS lock_expired
        FROM users
        WHERE username = %s AND is_active = 1
        """,
        (username,),
    )


def _register_failed_attempt(user_id: int) -> None:
    # One atomic statement (no read-modify-write race). MySQL evaluates SET clauses left
    # to right, so locked_until must come BEFORE failed_attempts to see the old count.
    run_action(
        """
        UPDATE users
        SET locked_until    = IF(failed_attempts + 1 >= %s,
                                 DATE_ADD(NOW(), INTERVAL %s MINUTE), locked_until),
            failed_attempts = failed_attempts + 1
        WHERE user_id = %s
        """,
        (config.MAX_LOGIN_ATTEMPTS, config.LOGIN_LOCKOUT_MINUTES, user_id),
    )


def attempt_login(username: str, password: str) -> tuple[bool, str]:
    """Returns (success, message). The message is always safe to show to the user."""
    username = (username or "").strip()
    if not username or not password:
        return False, "Please enter your username and password."

    try:
        user = _get_user(username)

        if user is None:
            burn_time()
            return False, GENERIC_LOGIN_ERROR

        if user["is_locked"]:
            burn_time()
            log.warning("Login blocked: account locked (user_id=%s)", user["user_id"])
            return False, GENERIC_LOGIN_ERROR

        if user["lock_expired"]:
            # A finished lockout starts a fresh counter (otherwise one typo would re-lock instantly).
            run_action("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = %s",
                       (user["user_id"],))

        if not verify_password(password, user["password_hash"]):
            _register_failed_attempt(user["user_id"])
            log.warning("Failed login (user_id=%s)", user["user_id"])
            return False, GENERIC_LOGIN_ERROR

        run_action(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login = NOW() WHERE user_id = %s",
            (user["user_id"],),
        )
    except DatabaseError:
        return False, UNAVAILABLE_MESSAGE

    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user["user_id"]
    st.session_state["username"] = user["username"]
    st.session_state["role"] = user["role"]
    st.session_state["last_active"] = datetime.now()
    log.info("Login success (user_id=%s)", user["user_id"])
    return True, "Login successful."


def logout() -> None:
    for key in ("authenticated", "user_id", "username", "role", "last_active"):
        st.session_state.pop(key, None)


# -------------------------------------------------------------- session ----
def is_session_expired() -> bool:
    last_active = st.session_state.get("last_active")
    if last_active is None:
        return True
    return datetime.now() - last_active > timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)


def touch_session() -> None:
    st.session_state["last_active"] = datetime.now()


def current_username() -> str | None:
    return st.session_state.get("username")


def current_role() -> str | None:
    return st.session_state.get("role")


def is_admin() -> bool:
    return current_role() == "admin"


def require_login() -> None:
    """Call at the top of every page. Stops the page unless a valid, active session exists."""
    if not st.session_state.get("authenticated"):
        st.warning("Please log in from the Home page to continue.")
        st.stop()

    if is_session_expired():
        logout()
        st.warning("Your session expired due to inactivity. Please log in again from the Home page.")
        st.stop()

    try:
        row = run_one("SELECT role, is_active FROM users WHERE user_id = %s",
                      (st.session_state.get("user_id"),))
    except DatabaseError as e:
        st.error(str(e))
        st.stop()

    if row is None or not row["is_active"]:
        logout()
        st.warning("Your account is no longer active. Please contact an administrator.")
        st.stop()

    st.session_state["role"] = row["role"]  # pick up role changes immediately
    touch_session()


def require_role(*roles: str) -> None:
    """Like require_login, but also stops the page unless the user has one of the roles."""
    require_login()
    if current_role() not in roles:
        st.error("You do not have permission to view this page.")
        st.stop()


def render_sidebar_user() -> None:
    with st.sidebar:
        st.markdown(f"**{current_username()}**  \n`{current_role()}`")
        if st.button("Log out", key="logout_btn"):
            logout()
            st.rerun()


# -------------------------------------------------------------- account ----
def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    """Change the logged-in user's own password."""
    problems = validate_password_strength(new_password, config.PASSWORD_MIN_LENGTH)
    if problems:
        return False, " ".join(problems)
    try:
        row = run_one("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
        if row is None or not verify_password(current_password, row["password_hash"]):
            return False, "Current password is incorrect."
        run_action("UPDATE users SET password_hash = %s WHERE user_id = %s",
                   (hash_password(new_password), user_id))
    except DatabaseError as e:
        return False, str(e)
    return True, "Password changed."
