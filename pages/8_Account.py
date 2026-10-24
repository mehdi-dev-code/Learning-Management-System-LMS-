import streamlit as st

import audit
from auth import change_password, current_username, is_admin
from config import config
from db import run_one
from security import hash_password, validate_password_strength
from utils.text import clean_text
from utils.ui import execute, form_version, get_options, paginated_table, reset_form, run_page
from utils.validators import show_errors, validate_username

ROLES = ["staff", "admin"]


def password_tab():
    st.subheader("Change my password")
    with st.form("change_password_form", clear_on_submit=True):
        current = st.text_input("Current password", type="password", key="cp_current")
        new = st.text_input("New password", type="password", key="cp_new",
                            help=f"At least {config.PASSWORD_MIN_LENGTH} characters, with a letter and a digit.")
        confirm = st.text_input("Confirm new password", type="password", key="cp_confirm")
        submitted = st.form_submit_button("Change password")

    if submitted:
        if new != confirm:
            st.error("The new passwords do not match.")
            return
        ok, message = change_password(st.session_state["user_id"], current, new)
        if ok:
            audit.record("password_change", "user", st.session_state["user_id"], "own password",
                         username=current_username())
            st.success(message)
        else:
            st.error(message)


def _other_active_admins(user_id: int) -> int:
    return run_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1 AND user_id <> %s",
                   (user_id,))["c"]


def users_tab():
    st.subheader("Users")
    paginated_table(
        "SELECT user_id, username, role, is_active, failed_attempts, locked_until, last_login, created_at "
        "FROM users ORDER BY user_id", key="users_page")

    st.divider()
    st.subheader("Create user")
    v = form_version("add_user")
    with st.form(f"add_user_form_{v}"):
        c1, c2 = st.columns(2)
        username = clean_text(c1.text_input("Username *", key=f"au_name_{v}"))
        role = c2.selectbox("Role", ROLES, key=f"au_role_{v}")
        password = c1.text_input("Password *", type="password", key=f"au_pw_{v}")
        confirm = c2.text_input("Confirm password *", type="password", key=f"au_pw2_{v}")
        submitted = st.form_submit_button("Create user")

    if submitted:
        errors: list[str] = []
        validate_username(username, errors)
        errors += validate_password_strength(password, config.PASSWORD_MIN_LENGTH)
        if password != confirm:
            errors.append("The passwords do not match.")
        if show_errors(errors):
            return
        if execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                   (username, hash_password(password), role),
                   success="User created.", action="create", entity="user", insert=True,
                   details=f"role={role}", use_flash=True):
            reset_form("add_user")
            st.rerun()

    st.divider()
    st.subheader("Manage user")
    options = get_options("SELECT user_id, username FROM users ORDER BY username", "user_id", ["username"])
    label = st.selectbox("Select user", list(options), key="mu_select")
    uid = options[label]
    record = run_one("SELECT user_id, username, role, is_active, locked_until FROM users WHERE user_id = %s",
                     (uid,))
    if record is None:
        st.warning("That user no longer exists. Please refresh the page.")
        return

    is_self = uid == st.session_state.get("user_id")
    with st.form(f"manage_user_{uid}"):
        c1, c2 = st.columns(2)
        new_role = c1.selectbox("Role", ROLES, index=ROLES.index(record["role"]), key=f"mu_role_{uid}")
        active = c2.checkbox("Account active", value=bool(record["is_active"]), key=f"mu_active_{uid}")
        saved = st.form_submit_button("Save changes")

    if saved:
        losing_admin = record["role"] == "admin" and record["is_active"] and (new_role != "admin" or not active)
        if is_self and (new_role != record["role"] or not active):
            st.error("You cannot demote or deactivate your own account.")
        elif losing_admin and _other_active_admins(uid) == 0:
            st.error("This is the last active administrator - at least one must remain.")
        elif execute("UPDATE users SET role = %s, is_active = %s WHERE user_id = %s",
                     (new_role, int(active), uid),
                     success="User updated.", action="update", entity="user", entity_id=uid,
                     details=f"role={new_role} active={int(active)}", use_flash=True):
            st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("Unlock account", key=f"mu_unlock_{uid}"):
        if execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = %s", (uid,),
                   success="Account unlocked.", action="unlock", entity="user", entity_id=uid, use_flash=True):
            st.rerun()

    with st.expander("Reset password"):
        with st.form(f"reset_pw_{uid}", clear_on_submit=True):
            pw1 = st.text_input("New password", type="password", key=f"rp_pw1_{uid}")
            pw2 = st.text_input("Confirm new password", type="password", key=f"rp_pw2_{uid}")
            reset = st.form_submit_button("Reset password")
        if reset:
            errors = validate_password_strength(pw1, config.PASSWORD_MIN_LENGTH)
            if pw1 != pw2:
                errors.append("The passwords do not match.")
            if not show_errors(errors):
                execute("UPDATE users SET password_hash = %s, failed_attempts = 0, locked_until = NULL "
                        "WHERE user_id = %s", (hash_password(pw1), uid),
                        success="Password reset. Tell the user to change it after logging in.",
                        action="password_reset", entity="user", entity_id=uid, details="by administrator")


def audit_tab():
    st.subheader("Audit log")
    st.caption("Who did what, newest first. Personal data is never stored in this log.")
    paginated_table("SELECT created_at, username, action, entity, entity_id, details "
                    "FROM audit_log ORDER BY log_id DESC", key="audit_page",
                    empty_message="No audit records yet.")


def main():
    st.title("👤 Account")
    if is_admin():
        tab_pw, tab_users, tab_audit = st.tabs(["Change Password", "Users", "Audit Log"])
        with tab_pw:
            password_tab()
        with tab_users:
            users_tab()
        with tab_audit:
            audit_tab()
    else:
        password_tab()


run_page("Account", main, icon="👤")
