"""
Input validation helpers. Each function APPENDS human-readable problems to the
`errors` list you pass in, so a form can show every problem at once.
"""

import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,50}$")


def validate_required(value: str, label: str, errors: list[str], max_length: int | None = None) -> None:
    if not value:
        errors.append(f"{label} is required.")
    elif max_length is not None and len(value) > max_length:
        errors.append(f"{label} must be at most {max_length} characters.")


def validate_email(value: str, errors: list[str], required: bool = True, max_length: int = 150) -> None:
    if not value:
        if required:
            errors.append("Email is required.")
        return
    if len(value) > max_length:
        errors.append(f"Email must be at most {max_length} characters.")
    elif not EMAIL_RE.match(value):
        errors.append("Email format is invalid.")


def validate_phone(value: str, errors: list[str], required: bool = False, max_length: int = 20) -> None:
    if not value:
        if required:
            errors.append("Phone number is required.")
        return
    digits = sum(ch.isdigit() for ch in value)
    if len(value) > max_length or not PHONE_RE.match(value) or not 7 <= digits <= 15:
        errors.append("Phone number must have 7-15 digits and may only contain digits, spaces, + - ( ).")


def validate_username(value: str, errors: list[str]) -> None:
    if not USERNAME_RE.match(value or ""):
        errors.append("Username must be 3-50 characters: letters, digits, dot, dash or underscore.")


def show_errors(errors: list[str]) -> bool:
    """Display errors in Streamlit. Returns True when there were errors."""
    import streamlit as st

    for message in errors:
        st.error(message)
    return bool(errors)
