"""
Page-level tests: each Streamlit page is executed with streamlit.testing.AppTest against a real
MySQL database, and widgets are clicked exactly like a user would.
"""

from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from security import verify_password
from utils.ui import NONE_LABEL

PAGES = Path(__file__).resolve().parent.parent / "pages"


# ---------------------------------------------------------------- helpers ----
def open_page(sql, name, user="admin1", **session):
    row = sql("SELECT user_id, role FROM users WHERE username = %s", (user,))[0]
    at = AppTest.from_file(str(PAGES / name), default_timeout=30)
    at.session_state["authenticated"] = True
    at.session_state["user_id"] = row["user_id"]
    at.session_state["username"] = user
    at.session_state["role"] = row["role"]
    at.session_state["last_active"] = datetime.now()
    for key, value in session.items():
        at.session_state[key] = value
    return at.run()


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def messages(elements):
    return " | ".join(e.value for e in elements)


def add_student(sql, first="Ali", last="Khan", email="ali@x.com", status="Active"):
    sql("INSERT INTO students (first_name, last_name, email, status) VALUES (%s, %s, %s, %s)",
        (first, last, email, status))
    return sql("SELECT LAST_INSERT_ID() AS i")[0]["i"]


def add_course(sql, name="Python", status="Active", instructor_id=None):
    sql("INSERT INTO courses (course_name, status, instructor_id) VALUES (%s, %s, %s)",
        (name, status, instructor_id))
    return sql("SELECT LAST_INSERT_ID() AS i")[0]["i"]


def add_enrollment(sql, sid, cid, status="Enrolled"):
    sql("INSERT INTO enrollments (student_id, course_id, status) VALUES (%s, %s, %s)", (sid, cid, status))
    return sql("SELECT LAST_INSERT_ID() AS i")[0]["i"]


# ------------------------------------------------------ session / access ----
def test_page_requires_login():
    at = AppTest.from_file(str(PAGES / "2_Students.py"), default_timeout=30).run()
    assert not at.exception and len(at.title) == 0
    assert "log in" in messages(at.warning).lower()


def test_expired_session_is_rejected(db, sql):
    at = open_page(sql, "2_Students.py", last_active=datetime.now() - timedelta(minutes=31))
    assert not at.exception and len(at.title) == 0
    assert "expired" in messages(at.warning)


def test_deactivated_user_is_logged_out_on_next_page_load(db, sql):
    sql("UPDATE users SET is_active = 0 WHERE username = 'staff1'")
    at = open_page(sql, "2_Students.py", user="staff1")
    assert len(at.title) == 0 and "no longer active" in messages(at.warning)


def test_role_comes_from_database_not_from_stale_session(db, sql):
    # Session claims "admin", but the database says staff -> admin-only tabs must not appear.
    at = open_page(sql, "8_Account.py", user="staff1", role="admin")
    assert not at.exception and len(at.tabs) == 0


# --------------------------------------------------------------- dashboard ----
def test_dashboard_works_on_empty_database(db, sql):
    at = open_page(sql, "1_Dashboard.py")
    assert not at.exception
    assert [m.value for m in at.metric] == ["0", "0", "0", "0"]
    assert "No enrollment data yet." in messages(at.info)


def test_dashboard_counts(db, sql):
    s1 = add_student(sql, "A", "A", "a@x.com")
    add_student(sql, "B", "B", "b@x.com", status="Inactive")
    c1 = add_course(sql)
    add_enrollment(sql, s1, c1)
    at = open_page(sql, "1_Dashboard.py")
    assert [m.value for m in at.metric] == ["2", "1", "0", "1"]


def test_writes_made_through_the_app_refresh_cached_pages_immediately(db, sql):
    assert [m.value for m in open_page(sql, "1_Dashboard.py").metric][0] == "0"   # now cached
    students = open_page(sql, "2_Students.py")
    fill_add_student(students, "Ali", "Khan", "ali@x.com")
    assert [m.value for m in open_page(sql, "1_Dashboard.py").metric][0] == "1"   # no waiting for the TTL


def test_database_outage_shows_one_friendly_message_not_a_traceback(db, sql, monkeypatch):
    from db import DatabaseError

    def boom(*args, **kwargs):
        raise DatabaseError("Could not connect to the database.")
    monkeypatch.setattr("utils.ui.run_query", boom)
    at = open_page(sql, "1_Dashboard.py")
    assert not at.exception
    assert messages(at.error) == "Could not connect to the database."


def test_unexpected_error_is_hidden_from_user_and_logged(db, sql, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr("utils.ui.run_query", boom)
    at = open_page(sql, "1_Dashboard.py")
    assert not at.exception
    assert "Something went wrong" in messages(at.error) and "secret" not in messages(at.error)


# ---------------------------------------------------------------- students ----
def fill_add_student(at, first, last, email, phone=""):
    version = next(t.key for t in at.text_input if t.key.startswith("as_first_")).rsplit("_", 1)[1]
    at.text_input(key=f"as_first_{version}").input(first)
    at.text_input(key=f"as_last_{version}").input(last)
    at.text_input(key=f"as_email_{version}").input(email)
    at.text_input(key=f"as_phone_{version}").input(phone)
    return click(at, "Add student")


def test_add_student_trims_normalises_and_audits(db, sql):
    at = open_page(sql, "2_Students.py")
    at = fill_add_student(at, "  Ali ", " Khan", "  ALI@Example.COM ", "")
    assert not at.exception and "Student added." in messages(at.success)
    row = sql("SELECT * FROM students")[0]
    assert (row["first_name"], row["last_name"], row["email"], row["phone"]) == ("Ali", "Khan", "ali@example.com", None)
    log = sql("SELECT * FROM audit_log")[0]
    assert (log["username"], log["action"], log["entity"]) == ("admin1", "create", "student")
    assert "ali" not in (log["details"] or "").lower()  # no personal data in the audit trail


def test_add_student_validation_blocks_bad_input(db, sql):
    at = open_page(sql, "2_Students.py")
    at = fill_add_student(at, "", "", "not-an-email", "12")
    text = messages(at.error)
    assert "First name is required" in text and "Last name is required" in text
    assert "Email format is invalid" in text and "Phone number" in text
    assert sql("SELECT COUNT(*) AS c FROM students")[0]["c"] == 0


def test_duplicate_email_gives_clear_message(db, sql):
    add_student(sql, email="ali@x.com")
    at = open_page(sql, "2_Students.py")
    at = fill_add_student(at, "Other", "Person", "ALI@x.com")
    assert "already exists" in messages(at.error)
    assert sql("SELECT COUNT(*) AS c FROM students")[0]["c"] == 1


def test_full_name_search_and_wildcard_escaping(db, sql):
    add_student(sql, "Ali", "Khan", "ali@x.com")
    add_student(sql, "Sara", "Ahmed", "sara@x.com")
    add_student(sql, "A%B", "Odd", "odd@x.com")
    at = open_page(sql, "2_Students.py")
    assert len(at.dataframe[0].value) == 3

    at.text_input(key="stu_search").input("Ali Khan").run()          # full name works now
    assert list(at.dataframe[0].value["first_name"]) == ["Ali"]

    at.text_input(key="stu_search").input("%").run()                 # '%' is NOT a wildcard
    assert list(at.dataframe[0].value["first_name"]) == ["A%B"]


def test_pagination_is_server_side_and_survives_filter_changes(db, sql):
    rows = [(f"S{i:02d}", "T", f"s{i}@{'a' if i < 30 else 'b'}.com") for i in range(60)]
    sql("INSERT INTO students (first_name, last_name, email) VALUES " + ",".join(["(%s,%s,%s)"] * 60),
        tuple(v for r in rows for v in r))
    at = open_page(sql, "2_Students.py")
    assert len(at.dataframe[0].value) == 25
    assert "Showing 1-25 of 60 records" in [c.value for c in at.caption]

    at.number_input(key="students_page").set_value(3).run()
    assert len(at.dataframe[0].value) == 10
    assert "Showing 51-60 of 60 records" in [c.value for c in at.caption]

    at.text_input(key="stu_search").input("@a.com").run()            # 30 rows = 2 pages, we were on page 3
    assert not at.exception and len(at.dataframe[0].value) == 25
    assert "Showing 1-25 of 30 records" in [c.value for c in at.caption]


def test_update_student_and_inactive_students_cannot_be_enrolled(db, sql):
    sid = add_student(sql)
    add_course(sql)
    at = open_page(sql, "2_Students.py")
    at.selectbox(key=f"us_status_{sid}").select("Inactive")
    at.text_input(key=f"us_phone_{sid}").input("+92 312 7627983")
    at = click(at, "Update student")
    assert "Student updated." in messages(at.success)
    row = sql("SELECT status, phone FROM students")[0]
    assert (row["status"], row["phone"]) == ("Inactive", "+92 312 7627983")

    at = open_page(sql, "5_Enrollments.py")
    assert "at least one Active student" in messages(at.info)


def test_student_with_enrollments_cannot_be_deleted_in_ui(db, sql):
    sid, cid = add_student(sql), add_course(sql)
    add_enrollment(sql, sid, cid)
    at = open_page(sql, "2_Students.py")
    assert "blocked" in messages(at.info)
    assert not [b for b in at.button if "Delete" in b.label]


def test_admin_can_delete_unused_student_staff_cannot(db, sql):
    sid = add_student(sql)
    staff = open_page(sql, "2_Students.py", user="staff1")
    assert not [b for b in staff.button if "Delete" in b.label]
    assert "Only administrators" in " ".join(c.value for c in staff.caption)

    at = open_page(sql, "2_Students.py")
    delete_btn = next(b for b in at.button if b.label == "Delete student permanently")
    assert delete_btn.disabled                                       # needs the confirmation tick first
    at.checkbox(key=f"stu_del_ok_{sid}").check().run()
    at = click(at, "Delete student permanently")
    assert sql("SELECT COUNT(*) AS c FROM students")[0]["c"] == 0
    assert sql("SELECT action FROM audit_log")[-1]["action"] == "delete"


# -------------------------------------------------------------- instructors ----
def test_instructor_phone_can_now_be_edited_and_is_validated(db, sql):
    sql("INSERT INTO instructors (first_name, last_name, email, phone) VALUES ('I', 'J', 'i@x.com', '111 2223333')")
    iid = sql("SELECT instructor_id FROM instructors")[0]["instructor_id"]
    at = open_page(sql, "3_Instructors.py")
    at.text_input(key=f"ui_phone_{iid}").input("abc")
    at = click(at, "Update instructor")
    assert "Phone number" in messages(at.error)
    at.text_input(key=f"ui_phone_{iid}").input("+92 300 1234567")
    at = click(at, "Update instructor")
    assert sql("SELECT phone FROM instructors")[0]["phone"] == "+92 300 1234567"


# ----------------------------------------------------------------- courses ----
def test_editing_a_course_without_instructor_keeps_it_without_instructor(db, sql):
    cid = add_course(sql, "Orphan", instructor_id=None)
    sql("INSERT INTO instructors (first_name, last_name, email) VALUES ('Zed', 'Zulu', 'z@x.com')")
    at = open_page(sql, "4_Courses.py")
    assert at.selectbox(key=f"uc_inst_{cid}").value == NONE_LABEL    # old bug: preselected the first instructor
    at.text_area(key=f"uc_desc_{cid}").input("New description")
    at = click(at, "Update course")
    row = sql("SELECT description, instructor_id FROM courses")[0]
    assert row["description"] == "New description" and row["instructor_id"] is None


def test_course_can_be_created_without_instructor_and_with_one(db, sql):
    sql("INSERT INTO instructors (first_name, last_name, email) VALUES ('Ayesha', 'Khan', 'a@x.com')")
    at = open_page(sql, "4_Courses.py")
    at.text_input(key="ac_name_0").input("No Teacher Yet")
    at = click(at, "Add course")
    assert sql("SELECT instructor_id FROM courses")[0]["instructor_id"] is None
    version = next(t.key for t in at.text_input if t.key.startswith("ac_name_")).rsplit("_", 1)[1]
    at.text_input(key=f"ac_name_{version}").input("With Teacher")
    at.selectbox(key=f"ac_inst_{version}").select_index(1)
    at = click(at, "Add course")
    assert sql("SELECT instructor_id FROM courses WHERE course_name = 'With Teacher'")[0]["instructor_id"] == 1


def test_course_with_enrollments_cannot_be_deleted(db, sql):
    sid, cid = add_student(sql), add_course(sql)
    add_enrollment(sql, sid, cid)
    at = open_page(sql, "4_Courses.py")
    assert "blocked" in messages(at.info) and not [b for b in at.button if "Delete" in b.label]


# ------------------------------------------------------------- enrollments ----
def test_enroll_prevents_duplicates_with_clear_message(db, sql):
    add_student(sql)
    add_course(sql)
    add_course(sql, "Inactive course", status="Inactive")
    at = open_page(sql, "5_Enrollments.py")
    assert len(at.selectbox(key="en_crs_0").options) == 1            # inactive course not offered
    at = click(at, "Enroll student")
    assert sql("SELECT COUNT(*) AS c FROM enrollments")[0]["c"] == 1
    at = click(at, "Enroll student")                                 # same student + course again
    assert "already enrolled" in messages(at.error)
    assert sql("SELECT COUNT(*) AS c FROM enrollments")[0]["c"] == 1


def test_enrollment_status_update_and_admin_only_delete(db, sql):
    sid, cid = add_student(sql), add_course(sql)
    eid = add_enrollment(sql, sid, cid)
    sql("INSERT INTO grades (enrollment_id, quiz_marks) VALUES (%s, 5)", (eid,))
    at = open_page(sql, "5_Enrollments.py")
    assert "permanently delete that grade" in messages(at.warning)
    at.selectbox(key=f"ue_status_{eid}").select("Dropped")
    at = click(at, "Update status")
    assert sql("SELECT status FROM enrollments")[0]["status"] == "Dropped"

    staff = open_page(sql, "5_Enrollments.py", user="staff1")
    assert not [b for b in staff.button if "Delete" in b.label]


# ------------------------------------------------------------------ grades ----
def test_grade_entry_uses_configured_maxima_and_upserts(db, sql):
    sid, cid = add_student(sql), add_course(sql)
    eid = add_enrollment(sql, sid, cid)
    at = open_page(sql, "6_Grades.py")
    a, q, f = (at.number_input(key=f"gr_{k}_{eid}") for k in "aqf")
    assert (a.max, q.max, f.max) == (20.0, 20.0, 60.0)
    a.set_value(15.0); q.set_value(18.0); f.set_value(50.0)
    at = click(at, "Save grade")
    assert "83 / 100" in messages(at.success) and "grade B" in messages(at.success)
    assert float(sql("SELECT total_marks FROM grades")[0]["total_marks"]) == 83.0

    at.number_input(key=f"gr_f_{eid}").set_value(60.0)               # save again -> update, not a 2nd row
    at = click(at, "Save grade")
    rows = sql("SELECT total_marks FROM grades")
    assert len(rows) == 1 and float(rows[0]["total_marks"]) == 93.0

    view = at.dataframe[0].value
    assert {"percentage", "grade"} <= set(view.columns) and view["grade"].iloc[0] == "A"


def test_dropped_enrollments_cannot_be_graded(db, sql):
    s1 = add_student(sql, "Active", "One", "a@x.com")
    s2 = add_student(sql, "Dropped", "Two", "d@x.com")
    cid = add_course(sql)
    add_enrollment(sql, s1, cid)
    add_enrollment(sql, s2, cid, status="Dropped")
    at = open_page(sql, "6_Grades.py")
    labels = at.selectbox(key="gr_select").options
    assert len(labels) == 1 and "Active One" in labels[0]


# ----------------------------------------------------------------- reports ----
def test_reports_empty_and_with_data(db, sql):
    at = open_page(sql, "7_Reports.py")
    assert not at.exception and "No data for this report yet." in messages(at.info)

    sid, cid = add_student(sql), add_course(sql)
    eid = add_enrollment(sql, sid, cid)
    sql("INSERT INTO grades (enrollment_id, assignment_marks, quiz_marks, final_exam_marks) VALUES (%s, 20, 20, 50)", (eid,))
    st.cache_data.clear()   # rows were inserted behind the app's back; the app clears the cache itself when IT writes
    at = open_page(sql, "7_Reports.py")
    assert not at.exception
    marks = next(df.value for df in at.dataframe if "total_marks" in df.value.columns)
    assert marks["grade"].iloc[0] == "A" and marks["percentage"].iloc[0] == 90.0


# ----------------------------------------------------------------- account ----
def test_account_tabs_by_role(db, sql):
    assert len(open_page(sql, "8_Account.py").tabs) == 3
    assert len(open_page(sql, "8_Account.py", user="staff1").tabs) == 0


def test_change_own_password_via_page(db, sql):
    at = open_page(sql, "8_Account.py", user="staff1")
    at.text_input(key="cp_current").input("wrong")
    at.text_input(key="cp_new").input("NewPassw0rd99")
    at.text_input(key="cp_confirm").input("NewPassw0rd99")
    at = click(at, "Change password")
    assert "incorrect" in messages(at.error)

    at.text_input(key="cp_current").input("CorrectHorse9")
    at.text_input(key="cp_new").input("NewPassw0rd99")
    at.text_input(key="cp_confirm").input("NewPassw0rd99")
    at = click(at, "Change password")
    assert "Password changed" in messages(at.success)
    pw_hash = sql("SELECT password_hash FROM users WHERE username = 'staff1'")[0]["password_hash"]
    assert verify_password("NewPassw0rd99", pw_hash)
    assert sql("SELECT action FROM audit_log")[-1]["action"] == "password_change"


def test_admin_creates_users_with_password_policy(db, sql):
    at = open_page(sql, "8_Account.py")
    at.text_input(key="au_name_0").input("newstaff")
    at.text_input(key="au_pw_0").input("weak")
    at.text_input(key="au_pw2_0").input("weak")
    at = click(at, "Create user")
    assert "at least" in messages(at.error)
    assert sql("SELECT COUNT(*) AS c FROM users WHERE username = 'newstaff'")[0]["c"] == 0

    version = next(t.key for t in at.text_input if t.key.startswith("au_name_")).rsplit("_", 1)[1]
    at.text_input(key=f"au_name_{version}").input("newstaff")
    at.text_input(key=f"au_pw_{version}").input("Str0ngPassword1")
    at.text_input(key=f"au_pw2_{version}").input("Str0ngPassword1")
    at = click(at, "Create user")
    row = sql("SELECT role, password_hash FROM users WHERE username = 'newstaff'")[0]
    assert row["role"] == "staff" and verify_password("Str0ngPassword1", row["password_hash"])


def test_admin_cannot_demote_or_deactivate_self_but_can_manage_others(db, sql):
    admin_id = sql("SELECT user_id FROM users WHERE username = 'admin1'")[0]["user_id"]
    staff_id = sql("SELECT user_id FROM users WHERE username = 'staff1'")[0]["user_id"]

    at = open_page(sql, "8_Account.py")
    at.selectbox(key="mu_select").select(next(o for o in at.selectbox(key="mu_select").options if "admin1" in o))
    at.run()
    at.checkbox(key=f"mu_active_{admin_id}").uncheck()
    at = click(at, "Save changes")
    assert "cannot demote or deactivate your own" in messages(at.error)
    assert sql("SELECT is_active FROM users WHERE username = 'admin1'")[0]["is_active"] == 1

    at.selectbox(key="mu_select").select(next(o for o in at.selectbox(key="mu_select").options if "staff1" in o))
    at.run()
    at.checkbox(key=f"mu_active_{staff_id}").uncheck()
    at = click(at, "Save changes")
    assert sql("SELECT is_active FROM users WHERE username = 'staff1'")[0]["is_active"] == 0


def test_admin_unlock_and_password_reset(db, sql):
    staff_id = sql("SELECT user_id FROM users WHERE username = 'staff1'")[0]["user_id"]
    sql("UPDATE users SET failed_attempts = 3, locked_until = NOW() + INTERVAL 10 MINUTE WHERE user_id = %s", (staff_id,))
    at = open_page(sql, "8_Account.py")
    at.selectbox(key="mu_select").select(next(o for o in at.selectbox(key="mu_select").options if "staff1" in o))
    at.run()
    at = click(at, "Unlock account")
    row = sql("SELECT failed_attempts, locked_until FROM users WHERE user_id = %s", (staff_id,))[0]
    assert row["failed_attempts"] == 0 and row["locked_until"] is None

    at.text_input(key=f"rp_pw1_{staff_id}").input("BrandNewPass77")
    at.text_input(key=f"rp_pw2_{staff_id}").input("BrandNewPass77")
    at = click(at, "Reset password")
    pw_hash = sql("SELECT password_hash FROM users WHERE user_id = %s", (staff_id,))[0]["password_hash"]
    assert verify_password("BrandNewPass77", pw_hash)


def test_audit_log_tab_lists_actions(db, sql):
    at = open_page(sql, "2_Students.py")
    fill_add_student(at, "Ali", "Khan", "ali@x.com")
    at = open_page(sql, "8_Account.py")
    audit_df = next(df.value for df in at.dataframe if "action" in df.value.columns)
    assert "create" in list(audit_df["action"]) and "admin1" in list(audit_df["username"])
