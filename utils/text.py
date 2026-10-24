"""Small text helpers shared by every page."""


def clean_text(value) -> str:
    """Trim whitespace; None becomes an empty string."""
    return (value or "").strip()


def normalize_email(value) -> str:
    """Trim and lowercase, so 'A@B.com ' and 'a@b.com' are the same address."""
    return clean_text(value).lower()


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so a search for '50%' or 'a_b' matches those characters literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
