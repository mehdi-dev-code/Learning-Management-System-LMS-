import pandas as pd
import streamlit as st

from queries import STATUS_BREAKDOWN_SQL
from utils.ui import cached_query, run_page

TOP_COURSES_SQL = """
    SELECT c.course_name, COUNT(e.enrollment_id) AS total_enrolled
    FROM courses c
    JOIN enrollments e ON c.course_id = e.course_id
    GROUP BY c.course_id, c.course_name
    ORDER BY total_enrolled DESC
    LIMIT 10
"""

COUNTS_SQL = """
    SELECT (SELECT COUNT(*) FROM students)                          AS total_students,
           (SELECT COUNT(*) FROM students WHERE status = 'Active')  AS active_students,
           (SELECT COUNT(*) FROM instructors)                       AS total_instructors,
           (SELECT COUNT(*) FROM courses)                           AS total_courses
"""


def main():
    st.title("📊 Academic Dashboard")

    counts = cached_query(COUNTS_SQL)[0]  # an aggregate query always returns exactly one row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Students", counts["total_students"])
    col2.metric("Active Students", counts["active_students"])
    col3.metric("Instructors", counts["total_instructors"])
    col4.metric("Courses", counts["total_courses"])

    st.markdown("---")
    left, right = st.columns(2)

    with left:
        st.subheader("Enrollment Status Breakdown")
        status_rows = cached_query(STATUS_BREAKDOWN_SQL)
        if status_rows:
            st.bar_chart(pd.DataFrame(status_rows).set_index("status"))
        else:
            st.info("No enrollment data yet.")

    with right:
        st.subheader("Top Courses by Enrollment")
        top_rows = cached_query(TOP_COURSES_SQL)
        if top_rows:
            st.bar_chart(pd.DataFrame(top_rows).set_index("course_name"))
        else:
            st.info("No enrollment data yet.")


run_page("Dashboard", main, icon="📊")
