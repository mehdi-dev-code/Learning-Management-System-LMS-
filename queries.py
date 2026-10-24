"""SQL that more than one page needs, kept in one place."""

from utils.text import escape_like
from utils.ui import get_options

STATUS_BREAKDOWN_SQL = """
    SELECT status, COUNT(*) AS total
    FROM enrollments
    GROUP BY status
    ORDER BY total DESC
"""


def enrollment_options(search: str = "", *, exclude_dropped: bool = False, limit: int = 200) -> dict[str, int]:
    """{label: enrollment_id} for selectboxes, optionally filtered by a student/course text search."""
    where, params = [], []
    if exclude_dropped:
        where.append("e.status <> 'Dropped'")
    if search:
        where.append("CONCAT(s.first_name, ' ', s.last_name, ' - ', c.course_name) LIKE %s")
        params.append(f"%{escape_like(search)}%")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT e.enrollment_id,
               CONCAT(s.first_name, ' ', s.last_name, ' - ', c.course_name) AS label
        FROM enrollments e
        JOIN students s ON s.student_id = e.student_id
        JOIN courses  c ON c.course_id  = e.course_id
        {where_sql}
        ORDER BY e.enrollment_id DESC
        LIMIT %s
    """
    return get_options(sql, "enrollment_id", ["label"], params + [limit])
