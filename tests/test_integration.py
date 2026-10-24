"""Integration tests: schema rules, the DB layer and authentication against a real MySQL server."""

import os
import time

import pytest
from streamlit.testing.v1 import AppTest

import auth
from db import DatabaseError, run_action, run_action_get_id, run_one, run_query, run_transaction


# ------------------------------------------------------------- DB layer ----
def test_run_query_raises_instead_of_returning_empty(db):
    # Old behaviour: returned [] (looked like "no records"). Now the caller is told.
    with pytest.raises(DatabaseError):
        run_query("SELECT * FROM table_that_does_not_exist")


def test_run_one_and_insert_id(db):
    new_id = run_action_get_id("INSERT INTO students (first_name, last_name, email) VALUES (%s, %s, %s)",
                               ("Ali", "Khan", "ali@x.com"))
    assert run_one("SELECT first_name FROM students WHERE student_id = %s", (new_id,))["first_name"] == "Ali"
    assert run_one("SELECT * FROM students WHERE student_id = %s", (999999,)) is None


def test_friendly_error_messages(db):
    run_action("INSERT INTO students (first_name, last_name, email) VALUES ('A', 'B', 'dup@x.com')")
    with pytest.raises(DatabaseError, match="already exists"):
        run_action("INSERT INTO students (first_name, last_name, email) VALUES ('C', 'D', 'DUP@x.com')")  # case-insensitive
    with pytest.raises(DatabaseError, match="too long"):
        run_action("INSERT INTO students (first_name, last_name, email) VALUES (%s, 'D', 'e@x.com')", ("x" * 101,))
    with pytest.raises(DatabaseError, match="allowed range"):
        run_action("INSERT INTO courses (course_name, fee) VALUES ('Bad', -5)")


def test_transaction_is_all_or_nothing(db):
    with pytest.raises(DatabaseError):
        run_transaction([
            ("INSERT INTO students (first_name, last_name, email) VALUES ('A', 'B', 'a@b.com')", ()),
            ("INSERT INTO students (first_name, last_name, email) VALUES ('A', 'B', 'a@b.com')", ()),  # duplicate
        ])
    assert run_one("SELECT COUNT(*) AS c FROM students")["c"] == 0


def test_no_personal_data_in_logs(db):
    marker = "leak-check-7731@example.com"
    run_action("INSERT INTO students (first_name, last_name, email) VALUES ('A', 'B', %s)", (marker,))
    with pytest.raises(DatabaseError):
        run_action("INSERT INTO students (first_name, last_name, email) VALUES ('A', 'B', %s)", (marker,))
    log_text = open(os.path.join(os.environ["LOG_DIR"], "lms.log"), encoding="utf-8").read()
    assert "Action failed" in log_text      # the failure WAS logged...
    assert marker not in log_text           # ...but without the parameter values


# ------------------------------------------------------- schema safety ----
def _seed_enrollment(sql):
    sql("INSERT INTO students (first_name, last_name, email) VALUES ('Ali', 'Khan', 'ali@x.com')")
    sql("INSERT INTO courses (course_name) VALUES ('Python')")
    sql("INSERT INTO enrollments (student_id, course_id) VALUES (1, 1)")
    sql("INSERT INTO grades (enrollment_id, assignment_marks, quiz_marks, final_exam_marks) VALUES (1, 15, 18, 50)")


def test_student_with_enrollments_cannot_be_deleted(db, sql):
    _seed_enrollment(sql)
    with pytest.raises(DatabaseError, match="Inactive"):
        run_action("DELETE FROM students WHERE student_id = 1")
    with pytest.raises(DatabaseError, match="Inactive"):
        run_action("DELETE FROM courses WHERE course_id = 1")
    assert run_one("SELECT COUNT(*) AS c FROM grades")["c"] == 1  # nothing was wiped


def test_deleting_enrollment_removes_only_its_grade(db, sql):
    _seed_enrollment(sql)
    run_action("DELETE FROM enrollments WHERE enrollment_id = 1")
    assert run_one("SELECT COUNT(*) AS c FROM grades")["c"] == 0
    assert run_one("SELECT COUNT(*) AS c FROM students")["c"] == 1


def test_deleting_instructor_leaves_course_without_instructor(db, sql):
    sql("INSERT INTO instructors (first_name, last_name, email) VALUES ('I', 'J', 'i@x.com')")
    sql("INSERT INTO courses (course_name, instructor_id) VALUES ('C', 1)")
    run_action("DELETE FROM instructors WHERE instructor_id = 1")
    assert run_one("SELECT instructor_id FROM courses")["instructor_id"] is None


def test_grade_constraints_and_generated_total(db, sql):
    _seed_enrollment(sql)
    assert float(run_one("SELECT total_marks FROM grades")["total_marks"]) == 83.0
    for bad in ("quiz_marks = -1", "assignment_marks = 100.5", "final_exam_marks = 250"):
        with pytest.raises(DatabaseError, match="allowed range"):
            run_action(f"UPDATE grades SET {bad}")


# ----------------------------------------------------------- authentication ----
def _login_script():
    import streamlit as st
    from auth import attempt_login
    st.session_state["result"] = attempt_login(st.session_state["u"], st.session_state["p"])


def login(username, password):
    at = AppTest.from_function(_login_script, default_timeout=30)
    at.session_state["u"], at.session_state["p"] = username, password
    at.run()
    assert not at.exception
    return at.session_state["result"], at


def test_login_success_sets_session_and_last_login(db, sql):
    (ok, _), at = login("admin1", "CorrectHorse9")
    assert ok and at.session_state["authenticated"] and at.session_state["role"] == "admin"
    assert sql("SELECT last_login FROM users WHERE username = 'admin1'")[0]["last_login"] is not None


def test_same_message_for_wrong_password_unknown_user_and_locked(db, sql):
    (_, wrong_pw), _ = login("admin1", "nope")
    (_, unknown), _ = login("ghost", "nope")
    for _ in range(3):
        login("staff1", "bad")
    (ok, locked_msg), _ = login("staff1", "CorrectHorse9")   # correct password, but locked
    assert not ok
    assert wrong_pw == unknown == locked_msg == auth.GENERIC_LOGIN_ERROR


def test_lockout_threshold_is_exact(db, sql):
    # MAX_LOGIN_ATTEMPTS=3: two failures must NOT lock, the third must.
    login("admin1", "bad"); login("admin1", "bad")
    row = sql("SELECT failed_attempts, locked_until FROM users WHERE username = 'admin1'")[0]
    assert row["failed_attempts"] == 2 and row["locked_until"] is None
    assert login("admin1", "CorrectHorse9")[0][0]            # still can log in -> counter resets
    assert sql("SELECT failed_attempts FROM users WHERE username = 'admin1'")[0]["failed_attempts"] == 0
    for _ in range(3):
        login("admin1", "bad")
    row = sql("SELECT failed_attempts, locked_until FROM users WHERE username = 'admin1'")[0]
    assert row["failed_attempts"] == 3 and row["locked_until"] is not None


def test_lock_expiry_starts_a_fresh_counter(db, sql):
    for _ in range(3):
        login("admin1", "bad")
    sql("UPDATE users SET locked_until = NOW() - INTERVAL 1 MINUTE WHERE username = 'admin1'")  # lock ran out
    login("admin1", "bad")   # ONE typo after the lock expired must not re-lock the account
    row = sql("SELECT failed_attempts, locked_until FROM users WHERE username = 'admin1'")[0]
    assert row["failed_attempts"] == 1 and row["locked_until"] is None
    assert login("admin1", "CorrectHorse9")[0][0]


def test_inactive_user_cannot_log_in(db, sql):
    sql("UPDATE users SET is_active = 0 WHERE username = 'staff1'")
    assert not login("staff1", "CorrectHorse9")[0][0]


def test_database_down_gives_friendly_message(db, monkeypatch):
    def boom(_):
        raise DatabaseError("Could not connect to the database.")
    monkeypatch.setattr(auth, "_get_user", boom)
    ok, message = login("admin1", "CorrectHorse9")[0]
    assert not ok and message == auth.UNAVAILABLE_MESSAGE


def test_unknown_user_takes_as_long_as_a_real_check(db):
    login("ghost", "x")                       # warm-up (creates the dummy hash)
    start = time.perf_counter()
    login("ghost", "x")
    unknown_time = time.perf_counter() - start
    assert unknown_time > 0.05                # bcrypt ran, so response time does not reveal the username


def test_change_password(db, sql):
    uid = sql("SELECT user_id FROM users WHERE username = 'staff1'")[0]["user_id"]
    ok, msg = auth.change_password(uid, "wrong-current", "NewPassw0rd99")
    assert not ok and "incorrect" in msg
    ok, msg = auth.change_password(uid, "CorrectHorse9", "weak")
    assert not ok
    ok, _ = auth.change_password(uid, "CorrectHorse9", "NewPassw0rd99")
    assert ok
    assert login("staff1", "NewPassw0rd99")[0][0] and not login("staff1", "CorrectHorse9")[0][0]
