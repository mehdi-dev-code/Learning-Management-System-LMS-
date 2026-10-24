from datetime import date

import streamlit as st

from auth import is_admin
from db import run_one
from utils.text import clean_text, escape_like, normalize_email
from utils.ui import execute, form_version, get_options, paginated_table, reset_form, run_page
from utils.validators import show_errors, validate_email, validate_phone, validate_required

STATUSES = ["Active", "Inactive"]


def _validate(first, last, email, phone) -> list[str]:
    errors: list[str] = []
    validate_required(first, "First name", errors, 100)
    validate_required(last, "Last name", errors, 100)
    validate_email(email, errors)
    validate_phone(phone, errors)
    return errors


def view_tab():
    col_search, col_status = st.columns([3, 1])
    search = clean_text(col_search.text_input("Search by name or email", key="stu_search"))
    status = col_status.selectbox("Status", ["All"] + STATUSES, key="stu_status")

    where, params = [], []
    if search:
        pattern = f"%{escape_like(search)}%"
        # CONCAT lets a full-name search such as "John Smith" work.
        where.append("(CONCAT(first_name, ' ', last_name) LIKE %s OR email LIKE %s)")
        params += [pattern, pattern]
    if status != "All":
        where.append("status = %s")
        params.append(status)

    sql = "SELECT * FROM students"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY student_id"
    paginated_table(sql, params, key="students_page", empty_message="No students found.")


def add_tab():
    v = form_version("add_student")
    with st.form(f"add_student_form_{v}"):
        c1, c2 = st.columns(2)
        first = clean_text(c1.text_input("First name *", key=f"as_first_{v}"))
        last = clean_text(c2.text_input("Last name *", key=f"as_last_{v}"))
        email = normalize_email(c1.text_input("Email *", key=f"as_email_{v}"))
        phone = clean_text(c2.text_input("Phone", key=f"as_phone_{v}"))
        enrolled_on = st.date_input("Enrollment date", value=date.today(), key=f"as_date_{v}")
        submitted = st.form_submit_button("Add student")

    if submitted:
        if show_errors(_validate(first, last, email, phone)):
            return
        if execute(
            "INSERT INTO students (first_name, last_name, email, phone, enrollment_date) "
            "VALUES (%s, %s, %s, %s, %s)",
            (first, last, email, phone or None, enrolled_on),
            success="Student added.", action="create", entity="student", insert=True, use_flash=True,
        ):
            reset_form("add_student")
            st.rerun()


def delete_section(sid: int):
    st.divider()
    st.subheader("Delete student")
    enrollments = run_one("SELECT COUNT(*) AS c FROM enrollments WHERE student_id = %s", (sid,))["c"]
    if enrollments:
        st.info(f"This student has {enrollments} enrollment(s), so permanent deletion is blocked. "
                "Set the status to **Inactive** instead - their history and grades stay intact.")
        return
    if not is_admin():
        st.caption("Only administrators can permanently delete records.")
        return
    confirmed = st.checkbox("I understand this permanently deletes the student.", key=f"stu_del_ok_{sid}")
    if st.button("Delete student permanently", key=f"stu_del_{sid}", disabled=not confirmed):
        if execute("DELETE FROM students WHERE student_id = %s", (sid,),
                   success="Student deleted.", action="delete", entity="student",
                   entity_id=sid, use_flash=True):
            st.rerun()


def update_tab():
    options = get_options(
        "SELECT student_id, first_name, last_name FROM students ORDER BY first_name, last_name",
        "student_id", ["first_name", "last_name"],
    )
    if not options:
        st.info("No students yet.")
        return

    label = st.selectbox("Select student", list(options), key="stu_select")
    sid = options[label]
    record = run_one("SELECT * FROM students WHERE student_id = %s", (sid,))
    if record is None:
        st.warning("That student no longer exists. Please refresh the page.")
        return

    with st.form(f"update_student_{sid}"):
        c1, c2 = st.columns(2)
        first = clean_text(c1.text_input("First name *", value=record["first_name"], key=f"us_first_{sid}"))
        last = clean_text(c2.text_input("Last name *", value=record["last_name"], key=f"us_last_{sid}"))
        email = normalize_email(c1.text_input("Email *", value=record["email"], key=f"us_email_{sid}"))
        phone = clean_text(c2.text_input("Phone", value=record["phone"] or "", key=f"us_phone_{sid}"))
        enrolled_on = c1.date_input("Enrollment date", value=record["enrollment_date"] or date.today(),
                                    key=f"us_date_{sid}")
        status = c2.selectbox("Status", STATUSES, index=STATUSES.index(record["status"]),
                              key=f"us_status_{sid}")
        submitted = st.form_submit_button("Update student")

    if submitted and not show_errors(_validate(first, last, email, phone)):
        if execute(
            "UPDATE students SET first_name=%s, last_name=%s, email=%s, phone=%s, "
            "enrollment_date=%s, status=%s WHERE student_id=%s",
            (first, last, email, phone or None, enrolled_on, status, sid),
            success="Student updated.", action="update", entity="student", entity_id=sid,
            details="fields edited", use_flash=True,
        ):
            st.rerun()

    delete_section(sid)


def main():
    st.title("🎓 Students")
    tab_view, tab_add, tab_update = st.tabs(["View / Search", "Add", "Update / Delete"])
    with tab_view:
        view_tab()
    with tab_add:
        add_tab()
    with tab_update:
        update_tab()


run_page("Students", main, icon="🎓")
