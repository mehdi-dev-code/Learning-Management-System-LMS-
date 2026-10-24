import streamlit as st

from auth import is_admin
from db import run_one
from utils.text import clean_text, escape_like, normalize_email
from utils.ui import execute, form_version, get_options, paginated_table, reset_form, run_page
from utils.validators import show_errors, validate_email, validate_phone, validate_required

STATUSES = ["Active", "Inactive"]


def _validate(first, last, specialization, email, phone) -> list[str]:
    errors: list[str] = []
    validate_required(first, "First name", errors, 100)
    validate_required(last, "Last name", errors, 100)
    if len(specialization) > 150:
        errors.append("Specialization must be at most 150 characters.")
    validate_email(email, errors)
    validate_phone(phone, errors)
    return errors


def view_tab():
    col_search, col_status = st.columns([3, 1])
    search = clean_text(col_search.text_input("Search by name, email or specialization", key="ins_search"))
    status = col_status.selectbox("Status", ["All"] + STATUSES, key="ins_status")

    where, params = [], []
    if search:
        pattern = f"%{escape_like(search)}%"
        where.append("(CONCAT(first_name, ' ', last_name) LIKE %s OR email LIKE %s OR specialization LIKE %s)")
        params += [pattern, pattern, pattern]
    if status != "All":
        where.append("status = %s")
        params.append(status)

    sql = "SELECT * FROM instructors"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY instructor_id"
    paginated_table(sql, params, key="instructors_page", empty_message="No instructors found.")


def add_tab():
    v = form_version("add_instructor")
    with st.form(f"add_instructor_form_{v}"):
        c1, c2 = st.columns(2)
        first = clean_text(c1.text_input("First name *", key=f"ai_first_{v}"))
        last = clean_text(c2.text_input("Last name *", key=f"ai_last_{v}"))
        specialization = clean_text(c1.text_input("Specialization", key=f"ai_spec_{v}"))
        email = normalize_email(c2.text_input("Email *", key=f"ai_email_{v}"))
        phone = clean_text(c1.text_input("Phone", key=f"ai_phone_{v}"))
        submitted = st.form_submit_button("Add instructor")

    if submitted:
        if show_errors(_validate(first, last, specialization, email, phone)):
            return
        if execute(
            "INSERT INTO instructors (first_name, last_name, specialization, email, phone) "
            "VALUES (%s, %s, %s, %s, %s)",
            (first, last, specialization or None, email, phone or None),
            success="Instructor added.", action="create", entity="instructor", insert=True, use_flash=True,
        ):
            reset_form("add_instructor")
            st.rerun()


def delete_section(iid: int):
    st.divider()
    st.subheader("Delete instructor")
    courses = run_one("SELECT COUNT(*) AS c FROM courses WHERE instructor_id = %s", (iid,))["c"]
    if not is_admin():
        st.caption("Only administrators can permanently delete records. Set the status to Inactive instead.")
        return
    if courses:
        st.warning(f"{courses} course(s) are taught by this instructor. If you delete them, those "
                   "courses stay but will have **no instructor**. Setting the status to Inactive is safer.")
    confirmed = st.checkbox("I understand this permanently deletes the instructor.", key=f"ins_del_ok_{iid}")
    if st.button("Delete instructor permanently", key=f"ins_del_{iid}", disabled=not confirmed):
        if execute("DELETE FROM instructors WHERE instructor_id = %s", (iid,),
                   success="Instructor deleted.", action="delete", entity="instructor",
                   entity_id=iid, details=f"{courses} course(s) left without instructor", use_flash=True):
            st.rerun()


def update_tab():
    options = get_options(
        "SELECT instructor_id, first_name, last_name FROM instructors ORDER BY first_name, last_name",
        "instructor_id", ["first_name", "last_name"],
    )
    if not options:
        st.info("No instructors yet.")
        return

    label = st.selectbox("Select instructor", list(options), key="ins_select")
    iid = options[label]
    record = run_one("SELECT * FROM instructors WHERE instructor_id = %s", (iid,))
    if record is None:
        st.warning("That instructor no longer exists. Please refresh the page.")
        return

    with st.form(f"update_instructor_{iid}"):
        c1, c2 = st.columns(2)
        first = clean_text(c1.text_input("First name *", value=record["first_name"], key=f"ui_first_{iid}"))
        last = clean_text(c2.text_input("Last name *", value=record["last_name"], key=f"ui_last_{iid}"))
        specialization = clean_text(c1.text_input("Specialization", value=record["specialization"] or "",
                                                  key=f"ui_spec_{iid}"))
        email = normalize_email(c2.text_input("Email *", value=record["email"], key=f"ui_email_{iid}"))
        phone = clean_text(c1.text_input("Phone", value=record["phone"] or "", key=f"ui_phone_{iid}"))
        status = c2.selectbox("Status", STATUSES, index=STATUSES.index(record["status"]),
                              key=f"ui_status_{iid}")
        submitted = st.form_submit_button("Update instructor")

    if submitted and not show_errors(_validate(first, last, specialization, email, phone)):
        if execute(
            "UPDATE instructors SET first_name=%s, last_name=%s, specialization=%s, email=%s, "
            "phone=%s, status=%s WHERE instructor_id=%s",
            (first, last, specialization or None, email, phone or None, status, iid),
            success="Instructor updated.", action="update", entity="instructor", entity_id=iid,
            details="fields edited", use_flash=True,
        ):
            st.rerun()

    delete_section(iid)


def main():
    st.title("👩‍🏫 Instructors")
    tab_view, tab_add, tab_update = st.tabs(["View / Search", "Add", "Update / Delete"])
    with tab_view:
        view_tab()
    with tab_add:
        add_tab()
    with tab_update:
        update_tab()


run_page("Instructors", main, icon="👩‍🏫")
