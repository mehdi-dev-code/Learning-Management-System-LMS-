import streamlit as st

from auth import is_admin
from db import run_one
from utils.text import clean_text, escape_like
from utils.ui import NONE_LABEL, execute, form_version, get_options, paginated_table, reset_form, run_page
from utils.validators import show_errors, validate_required

STATUSES = ["Active", "Inactive"]
MAX_FEE = 99_999_999.99  # DECIMAL(10,2)


def _validate(name, description, duration) -> list[str]:
    errors: list[str] = []
    validate_required(name, "Course name", errors, 150)
    if len(duration) > 50:
        errors.append("Duration must be at most 50 characters.")
    return errors


def _instructor_options(include_id: int | None = None) -> dict[str, int | None]:
    """{label: instructor_id}; 'None' first. Active instructors, plus the course's current one."""
    options = {NONE_LABEL: None}
    options.update(get_options(
        "SELECT instructor_id, first_name, last_name FROM instructors "
        "WHERE status = 'Active' OR instructor_id = %s ORDER BY first_name, last_name",
        "instructor_id", ["first_name", "last_name"], (include_id or 0,),
    ))
    return options


def view_tab():
    col_search, col_status = st.columns([3, 1])
    search = clean_text(col_search.text_input("Search by course name", key="crs_search"))
    status = col_status.selectbox("Status", ["All"] + STATUSES, key="crs_status")

    where, params = [], []
    if search:
        where.append("c.course_name LIKE %s")
        params.append(f"%{escape_like(search)}%")
    if status != "All":
        where.append("c.status = %s")
        params.append(status)

    sql = """
        SELECT c.course_id, c.course_name, c.description,
               CONCAT(i.first_name, ' ', i.last_name) AS instructor,
               c.duration, c.fee, c.status
        FROM courses c LEFT JOIN instructors i ON i.instructor_id = c.instructor_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.course_id"
    paginated_table(sql, params, key="courses_page", empty_message="No courses found.")


def add_tab():
    options = _instructor_options()
    v = form_version("add_course")
    with st.form(f"add_course_form_{v}"):
        name = clean_text(st.text_input("Course name *", key=f"ac_name_{v}"))
        description = clean_text(st.text_area("Description", key=f"ac_desc_{v}"))
        c1, c2, c3 = st.columns(3)
        instructor_label = c1.selectbox("Instructor", list(options), key=f"ac_inst_{v}")
        duration = clean_text(c2.text_input("Duration (e.g. 8 weeks)", key=f"ac_dur_{v}"))
        fee = c3.number_input("Fee", min_value=0.0, max_value=MAX_FEE, step=500.0, format="%.2f",
                              key=f"ac_fee_{v}")
        submitted = st.form_submit_button("Add course")

    if submitted:
        if show_errors(_validate(name, description, duration)):
            return
        if execute(
            "INSERT INTO courses (course_name, description, instructor_id, duration, fee) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, description or None, options[instructor_label], duration or None, fee),
            success="Course added.", action="create", entity="course", insert=True, use_flash=True,
        ):
            reset_form("add_course")
            st.rerun()


def delete_section(cid: int):
    st.divider()
    st.subheader("Delete course")
    enrollments = run_one("SELECT COUNT(*) AS c FROM enrollments WHERE course_id = %s", (cid,))["c"]
    if enrollments:
        st.info(f"This course has {enrollments} enrollment(s), so permanent deletion is blocked. "
                "Set the status to **Inactive** instead - enrollment history and grades stay intact.")
        return
    if not is_admin():
        st.caption("Only administrators can permanently delete records.")
        return
    confirmed = st.checkbox("I understand this permanently deletes the course.", key=f"crs_del_ok_{cid}")
    if st.button("Delete course permanently", key=f"crs_del_{cid}", disabled=not confirmed):
        if execute("DELETE FROM courses WHERE course_id = %s", (cid,),
                   success="Course deleted.", action="delete", entity="course",
                   entity_id=cid, use_flash=True):
            st.rerun()


def update_tab():
    course_options = get_options("SELECT course_id, course_name FROM courses ORDER BY course_name",
                                 "course_id", ["course_name"])
    if not course_options:
        st.info("No courses yet.")
        return

    label = st.selectbox("Select course", list(course_options), key="crs_select")
    cid = course_options[label]
    record = run_one("SELECT * FROM courses WHERE course_id = %s", (cid,))
    if record is None:
        st.warning("That course no longer exists. Please refresh the page.")
        return

    instructors = _instructor_options(record["instructor_id"])
    labels = list(instructors)
    # A course whose instructor was removed has instructor_id NULL -> preselect "None" (index 0),
    # so saving the form can never silently assign somebody else.
    current_index = next((i for i, lab in enumerate(labels) if instructors[lab] == record["instructor_id"]), 0)

    with st.form(f"update_course_{cid}"):
        name = clean_text(st.text_input("Course name *", value=record["course_name"], key=f"uc_name_{cid}"))
        description = clean_text(st.text_area("Description", value=record["description"] or "",
                                              key=f"uc_desc_{cid}"))
        c1, c2, c3, c4 = st.columns(4)
        instructor_label = c1.selectbox("Instructor", labels, index=current_index, key=f"uc_inst_{cid}")
        duration = clean_text(c2.text_input("Duration", value=record["duration"] or "", key=f"uc_dur_{cid}"))
        fee = c3.number_input("Fee", min_value=0.0, max_value=MAX_FEE, step=500.0, format="%.2f",
                              value=float(record["fee"]), key=f"uc_fee_{cid}")
        status = c4.selectbox("Status", STATUSES, index=STATUSES.index(record["status"]),
                              key=f"uc_status_{cid}")
        submitted = st.form_submit_button("Update course")

    if submitted and not show_errors(_validate(name, description, duration)):
        if execute(
            "UPDATE courses SET course_name=%s, description=%s, instructor_id=%s, duration=%s, "
            "fee=%s, status=%s WHERE course_id=%s",
            (name, description or None, instructors[instructor_label], duration or None, fee, status, cid),
            success="Course updated.", action="update", entity="course", entity_id=cid,
            details="fields edited", use_flash=True,
        ):
            st.rerun()

    delete_section(cid)


def main():
    st.title("📚 Courses")
    tab_view, tab_add, tab_update = st.tabs(["View / Search", "Add", "Update / Delete"])
    with tab_view:
        view_tab()
    with tab_add:
        add_tab()
    with tab_update:
        update_tab()


run_page("Courses", main, icon="📚")
