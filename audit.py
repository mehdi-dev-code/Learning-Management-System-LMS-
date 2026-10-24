"""
audit.py
Append-only audit trail: who did what, to which record, and when.
Details must never contain personal data (names, emails, phone numbers) -
log field names and record IDs only.
"""

from db import DatabaseError, run_action
from logger import get_logger

log = get_logger(__name__)


def record(action: str, entity: str, entity_id: int | None = None,
           details: str = "", username: str | None = None) -> None:
    """Best-effort: a failing audit write is logged but never blocks the user's action."""
    try:
        run_action(
            "INSERT INTO audit_log (username, action, entity, entity_id, details) "
            "VALUES (%s, %s, %s, %s, %s)",
            (username, action[:30], entity[:30], entity_id, details[:500]),
        )
    except DatabaseError:
        log.error("Could not write audit record: %s %s %s", action, entity, entity_id)
