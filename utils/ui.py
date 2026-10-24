"""
Shared Streamlit helpers: page wrapper, flash messages, cached lookups,
server-side pagination and audited write operations.
"""

import pandas as pd
import streamlit as st

import audit
from auth import current_username, render_sidebar_user, require_login, require_role
from config import config
from db import DatabaseError, run_action, run_action_get_id, run_one, run_query
from logger import get_logger

log = get_logger(__name__)

NONE_LABEL = "— None —"
_FLASH_KEY = "_flash_messages"


# ------------------------------------------------------------ page shell ----
def run_page(title: str, main, *, icon: str = "📚", roles: tuple[str, ...] | None = None) -> None:
    """Standard page wrapper: layout, login/role check, flash messages and error handling.

    A database outage shows ONE friendly error message instead of a traceback, and any
    unexpected exception is logged while the user only sees a generic message.
    """
    st.set_page_config(page_title=f"{title} - LMS", page_icon=icon, layout="wide")
    if roles:
        require_role(*roles)
    else:
        require_login()
    render_sidebar_user()
    _show_flash()
    try:
        main()
    except DatabaseError as e:
        st.error(str(e))
    except Exception:
        log.exception("Unhandled error on page '%s'", title)
        st.error("Something went wrong. The error was logged - please try again or contact an administrator.")


def flash(message: str, kind: str = "success") -> None:
    """Queue a message to show at the top of the NEXT run (survives st.rerun())."""
    st.session_state.setdefault(_FLASH_KEY, []).append((kind, message))


def _show_flash() -> None:
    for kind, message in st.session_state.pop(_FLASH_KEY, []):
        getattr(st, kind)(message)


def form_version(name: str) -> int:
    return st.session_state.get(f"_ver_{name}", 0)


def reset_form(name: str) -> None:
    """Give a form fresh (empty) widgets - used after a SUCCESSFUL submit only."""
    st.session_state[f"_ver_{name}"] = form_version(name) + 1


# ---------------------------------------------------------------- cache ----
@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner=False)
def _cached(query: str, params: tuple) -> list[dict]:
    return run_query(query, params)


def cached_query(query: str, params: tuple | list = ()) -> list[dict]:
    """SELECT with a short-lived cache (lookups, dashboard, reports)."""
    return _cached(query, tuple(params))


def invalidate_cache() -> None:
    st.cache_data.clear()


def get_options(query: str, id_col: str, label_cols: list[str], params: tuple | list = ()) -> dict[str, int]:
    """Build {label: id} for a selectbox. Labels include the ID so duplicates stay distinct."""
    options = {}
    for row in cached_query(query, params):
        label = " ".join(str(row[c]) for c in label_cols)
        options[f"{label} (ID: {row[id_col]})"] = row[id_col]
    return options


# --------------------------------------------------------------- writes ----
def execute(query: str, params: tuple | list, *, success: str, action: str, entity: str,
            entity_id: int | None = None, details: str = "", insert: bool = False,
            use_flash: bool = False) -> bool:
    """Run one write, clear caches, write the audit record and report the result.

    Returns True on success. On failure the (user-safe) database message is shown.
    With use_flash=True the success message survives the st.rerun() that follows.
    """
    try:
        if insert:
            entity_id = run_action_get_id(query, params)
        else:
            run_action(query, params)
    except DatabaseError as e:
        st.error(str(e))
        return False

    invalidate_cache()
    audit.record(action, entity, entity_id, details, username=current_username())
    if use_flash:
        flash(success)
    else:
        st.success(success)
    return True


# ----------------------------------------------------------- pagination ----
def paginated_table(select_sql: str, params: tuple | list = (), *, key: str,
                    transform=None, empty_message: str = "No records found.") -> int:
    """Show a table using SQL LIMIT/OFFSET - only ONE page of rows is fetched per run.

    `select_sql` must include its own ORDER BY. Returns the total number of rows.
    """
    page_size = config.PAGE_SIZE
    params = tuple(params)

    total = run_one(f"SELECT COUNT(*) AS c FROM ({select_sql}) AS counted", params)["c"]
    if total == 0:
        st.info(empty_message)
        return 0

    total_pages = (total - 1) // page_size + 1
    if total_pages > 1:
        if st.session_state.get(key, 1) > total_pages:  # filters narrowed the result set
            st.session_state[key] = 1
        page = int(st.number_input(f"Page (1-{total_pages})", min_value=1, max_value=total_pages,
                                   step=1, key=key))
    else:
        page = 1

    offset = (page - 1) * page_size
    rows = run_query(f"{select_sql} LIMIT %s OFFSET %s", params + (page_size, offset))
    df = pd.DataFrame(rows)
    if transform is not None:
        df = transform(df)

    st.dataframe(df, width="stretch", hide_index=True)
    st.caption(f"Showing {offset + 1}-{offset + len(rows)} of {total} records")
    return total
