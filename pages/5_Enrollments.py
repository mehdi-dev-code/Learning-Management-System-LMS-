from datetime import date

import streamlit as st

from auth import is_admin
from db import run_one
from queries import enrollment_options
from utils.text import clean_text, escape_like
from utils.ui import execute, form_version, get_options, paginated_table, reset_form, run_page

STATUSES = ["Enrolled", "Completed", "Dropped"]


def view_tab():
    col_search, col_status = st.columns([3, 1])
    search = clean_text(col_search.text_input("Search by student or course", key="enr_search"))
    status = col_status.selectbox("Status", ["All"] + STATUSES, key="enr_status")

    where, params = [], []
    if search:
        where.append("CONCAT(s.first_name, ' ', s.last_name, ' - ', c.course_name) LIKE %s")
        params.append(f"%{escape_like(search)}%")
    if status != "All":
        where.append("e.status = %s")
        params.append(status)

    sql = """
        SELECT e.enrollment_id,
               CONCAT(s.first_name, ' ', s.last_name) AS student,
               c.course_name, e.enrollment_date, e.status
        FROM enrollments e
        JOIN students s ON s.student_id = e.student_id
        JOIN courses  c ON c.course_id  = e.course_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.enrollment_id DESC"
    paginated_table(sql, params, key="enrollments_page", empty_message="No enrollments found.")


def enroll_tab():
    # Only ACTIVE students and courses can be enrolled.
    students = get_options(
        "SELECT student_id, first_name, last_name FROM students WHERE status = 'Active' "
        "ORDER BY first_name, last_name", "student_id", ["first_name", "last_name"])
    courses = get_options(
        "SELECT course_id, course_name FROM courses WHERE status = 'Active' ORDER BY course_name",
        "course_id", ["course_name"])
    if not students or not courses:
        st.info("You need at least one Active student and one Active course before enrolling.")
        return

    v = form_version("enroll")
    with st.form(f"enroll_form_{v}"):
        student_label = st.selectbox("Student", list(students), key=f"en_stu_{v}")
        course_label = st.selectbox("Course", list(courses), key=f"en_crs_{v}")
        enrolled_on = st.date_input("Enrollment date", value=date.today(), key=f"en_date_{v}")
        submitted = st.form_submit_button("Enroll student")

    if submitted:
        sid, cid = students[student_label], courses[course_label]
        existing = run_one("SELECT status FROM enrollments WHERE student_id = %s AND course_id = %s",
                           (sid, cid))
        if existing:
            st.error(f"This student is already enrolled in this course (status: {existing['status']}). "
                     "Use the Update tab to change the status.")
            return
        if execute(
            "INSERT INTO enrollments (student_id, course_id, enrollment_date) VALUES (%s, %s, %s)",
            (sid, cid, enrolled_on),
            success="Student enrolled.", action="create", entity="enrollment", insert=True,
            details=f"student_id={sid} course_id={cid}", use_flash=True,
        ):
            reset_form("enroll")
            st.rerun()


def remove_section(eid: int):
    st.divider()
    st.subheader("Remove enrollment")
    if not is_admin():
        st.caption("Only administrators can delete enrollments. Use the status **Dropped** instead.")
        return
    grade = run_one("SELECT grade_id FROM grades WHERE enrollment_id = %s", (eid,))
    if grade:
        st.warning("This enrollment has a grade record. Deleting the enrollment will also "
                   "**permanently delete that grade**. Setting the status to Dropped is safer.")
    confirmed = st.checkbox("I understand this permanently deletes the enrollment.", key=f"enr_del_ok_{eid}")
    if st.button("Delete enrollment permanently", key=f"enr_del_{eid}", disabled=not confirmed):
        if execute("DELETE FROM enrollments WHERE enrollment_id = %s", (eid,),
                   success="Enrollment deleted.", action="delete", entity="enrollment", entity_id=eid,
                   details="grade deleted too" if grade else "", use_flash=True):
            st.rerun()


def update_tab():
    search = clean_text(st.text_input("Filter the list by student or course name", key="enr_filter"))
    options = enrollment_options(search)
    if not options:
        st.info("No enrollments match.")
        return
    st.caption("Showing the most recent matches - type in the filter above to narrow the list.")

    label = st.selectbox("Select enrollment", list(options), key="enr_select")
    eid = options[label]
    record = run_one("SELECT enrollment_id, status FROM enrollments WHERE enrollment_id = %s", (eid,))
    if record is None:
        st.warning("That enrollment no longer exists. Please refresh the page.")
        return

    with st.form(f"update_enrollment_{eid}"):
        status = st.selectbox("Status", STATUSES, index=STATUSES.index(record["status"]),
                              key=f"ue_status_{eid}")
        submitted = st.form_submit_button("Update status")

    if submitted:
        if execute("UPDATE enrollments SET status = %s WHERE enrollment_id = %s", (status, eid),
                   success="Enrollment updated.", action="update", entity="enrollment", entity_id=eid,
                   details=f"status={status}", use_flash=True):
            st.rerun()

    remove_section(eid)


def main():
    st.title("📝 Enrollments")
    tab_view, tab_enroll, tab_update = st.tabs(["View", "Enroll Student", "Update / Remove"])
    with tab_view:
        view_tab()
    with tab_enroll:
        enroll_tab()
    with tab_update:
        update_tab()


run_page("Enrollments", main, icon="📝")
