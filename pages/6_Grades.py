import streamlit as st

from auth import is_admin
from config import config
from db import run_one
from queries import enrollment_options
from utils.grading import add_grade_columns, letter_grade, percentage
from utils.text import clean_text
from utils.ui import execute, paginated_table, run_page


def view_tab():
    st.caption(f"Marks scheme: assignments /{config.GRADE_MAX_ASSIGNMENT:g} + quizzes /{config.GRADE_MAX_QUIZ:g} "
               f"+ final exam /{config.GRADE_MAX_FINAL:g} = /{config.GRADE_TOTAL_MAX:g}")
    sql = """
        SELECT g.grade_id,
               CONCAT(s.first_name, ' ', s.last_name) AS student,
               c.course_name, e.status AS enrollment_status,
               g.assignment_marks, g.quiz_marks, g.final_exam_marks, g.total_marks
        FROM grades g
        JOIN enrollments e ON e.enrollment_id = g.enrollment_id
        JOIN students s ON s.student_id = e.student_id
        JOIN courses  c ON c.course_id  = e.course_id
        ORDER BY g.updated_at DESC, g.grade_id DESC
    """
    paginated_table(sql, key="grades_page", transform=add_grade_columns, empty_message="No grades recorded yet.")


def delete_section(eid: int):
    if not is_admin():
        return
    st.divider()
    st.subheader("Delete grade")
    confirmed = st.checkbox("I understand this permanently deletes the grade record.", key=f"gr_del_ok_{eid}")
    if st.button("Delete grade", key=f"gr_del_{eid}", disabled=not confirmed):
        if execute("DELETE FROM grades WHERE enrollment_id = %s", (eid,),
                   success="Grade deleted.", action="delete", entity="grade", entity_id=eid, use_flash=True):
            st.rerun()


def entry_tab():
    search = clean_text(st.text_input("Filter the list by student or course name", key="gr_filter"))
    # Grades cannot be entered for DROPPED enrollments.
    options = enrollment_options(search, exclude_dropped=True)
    if not options:
        st.info("No eligible enrollments (dropped enrollments cannot be graded).")
        return

    label = st.selectbox("Select enrollment", list(options), key="gr_select")
    eid = options[label]
    existing = run_one(
        "SELECT assignment_marks, quiz_marks, final_exam_marks, total_marks FROM grades WHERE enrollment_id = %s",
        (eid,))

    if existing:
        pct = percentage(existing["total_marks"])
        st.info(f"Current grade: **{existing['total_marks']} / {config.GRADE_TOTAL_MAX:g}** "
                f"({pct}% - grade {letter_grade(pct)})")

    def _val(column):
        return float(existing[column]) if existing else 0.0

    with st.form(f"grade_form_{eid}"):
        c1, c2, c3 = st.columns(3)
        assignment = c1.number_input(f"Assignments (max {config.GRADE_MAX_ASSIGNMENT:g})", min_value=0.0,
                                     max_value=config.GRADE_MAX_ASSIGNMENT, step=0.5, format="%.2f",
                                     value=min(_val("assignment_marks"), config.GRADE_MAX_ASSIGNMENT),
                                     key=f"gr_a_{eid}")
        quiz = c2.number_input(f"Quizzes (max {config.GRADE_MAX_QUIZ:g})", min_value=0.0,
                               max_value=config.GRADE_MAX_QUIZ, step=0.5, format="%.2f",
                               value=min(_val("quiz_marks"), config.GRADE_MAX_QUIZ), key=f"gr_q_{eid}")
        final = c3.number_input(f"Final exam (max {config.GRADE_MAX_FINAL:g})", min_value=0.0,
                                max_value=config.GRADE_MAX_FINAL, step=0.5, format="%.2f",
                                value=min(_val("final_exam_marks"), config.GRADE_MAX_FINAL), key=f"gr_f_{eid}")
        submitted = st.form_submit_button("Save grade")

    if submitted:
        total = assignment + quiz + final
        pct = percentage(total)
        # One atomic statement: creates the grade or updates the existing one (no check-then-insert race).
        if execute(
            "INSERT INTO grades (enrollment_id, assignment_marks, quiz_marks, final_exam_marks) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE assignment_marks = VALUES(assignment_marks), "
            "quiz_marks = VALUES(quiz_marks), final_exam_marks = VALUES(final_exam_marks)",
            (eid, assignment, quiz, final),
            success=f"Grade saved: {total:g} / {config.GRADE_TOTAL_MAX:g} ({pct}% - grade {letter_grade(pct)}).",
            action="grade_save", entity="grade", entity_id=eid, use_flash=True,
        ):
            st.rerun()

    if existing:
        delete_section(eid)


def main():
    st.title("🏆 Grades")
    tab_view, tab_entry = st.tabs(["View Grades", "Enter / Update Grade"])
    with tab_view:
        view_tab()
    with tab_entry:
        entry_tab()


run_page("Grades", main, icon="🏆")
