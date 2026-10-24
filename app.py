"""
app.py - entry point / login page.   Run with:  streamlit run app.py
"""

import streamlit as st

from auth import attempt_login, current_role, current_username, render_sidebar_user, require_login

st.set_page_config(page_title="LMS", page_icon="🎓", layout="wide")


def show_login() -> None:
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.markdown("<h2 style='text-align: center;'>🔐 LMS Login</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", width="stretch")
        if submitted:
            success, message = attempt_login(username, password)
            if success:
                st.rerun()
            st.error(message)


def show_home() -> None:
    require_login()  # re-validates the session and that the account is still active
    render_sidebar_user()

    st.title("🎓 Learning Management System")
    st.write(f"Welcome, **{current_username()}** ({current_role()}).")
    st.write("Use the sidebar to open a section:")
    st.markdown(
        "- **Dashboard** - key numbers at a glance\n"
        "- **Students / Instructors / Courses** - manage records\n"
        "- **Enrollments** - enroll students in courses\n"
        "- **Grades** - enter and review marks\n"
        "- **Reports** - management reports with CSV export\n"
        "- **Account** - change your password (administrators also manage users and see the audit log)"
    )


if st.session_state.get("authenticated"):
    show_home()
else:
    show_login()
