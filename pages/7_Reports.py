import pandas as pd
import streamlit as st

from queries import STATUS_BREAKDOWN_SQL
from utils.export import df_to_safe_csv
from utils.grading import add_grade_columns
from utils.ui import cached_query, run_page

# (title, SQL, optional post-processing)
REPORTS = [
    ("BR-01: Courses with Highest Enrollment", """
        SELECT c.course_name, COUNT(e.enrollment_id) AS total_enrolled
        FROM courses c JOIN enrollments e ON c.course_id = e.course_id
        GROUP BY c.course_id, c.course_name ORDER BY total_enrolled DESC
    """, None),
    ("BR-02: Courses Taught Per Instructor", """
        SELECT i.first_name, i.last_name, COUNT(c.course_id) AS courses_taught
        FROM instructors i LEFT JOIN courses c ON i.instructor_id = c.instructor_id
        GROUP BY i.instructor_id, i.first_name, i.last_name ORDER BY courses_taught DESC
    """, None),
    ("BR-03: Students with Highest Total Marks (top 100)", """
        SELECT s.first_name, s.last_name, c.course_name, g.total_marks
        FROM grades g
        JOIN enrollments e ON g.enrollment_id = e.enrollment_id
        JOIN students s ON e.student_id = s.student_id
        JOIN courses c ON e.course_id = c.course_id
        ORDER BY g.total_marks DESC
        LIMIT 100
    """, add_grade_columns),
    ("BR-04: Active Students Count",
     "SELECT COUNT(*) AS active_students_count FROM students WHERE status = 'Active'", None),
    ("BR-05: Enrollment Status Breakdown", STATUS_BREAKDOWN_SQL, None),
    ("BR-06: Courses with No Students Enrolled", """
        SELECT c.course_id, c.course_name
        FROM courses c LEFT JOIN enrollments e ON c.course_id = e.course_id
        WHERE e.enrollment_id IS NULL
        ORDER BY c.course_id
    """, None),
]


def main():
    st.title("📈 Management Reports")

    for title, query, post in REPORTS:
        code = title.split(":")[0]
        st.subheader(title)
        df = pd.DataFrame(cached_query(query))
        if post is not None:
            df = post(df)
        if df.empty:
            st.info("No data for this report yet.")
        else:
            st.dataframe(df, width="stretch", hide_index=True)
            st.download_button(
                label=f"Export {code} CSV",
                data=df_to_safe_csv(df),
                file_name=f"{code.lower().replace('-', '_')}.csv",
                mime="text/csv",
                key=f"download_{code}",
            )
        st.divider()


run_page("Reports", main, icon="📈")
