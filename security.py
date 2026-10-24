"""
security.py
Password hashing and password-policy checks. Deliberately has NO Streamlit
import, so command-line scripts can use it without loading the web framework.
"""

import bcrypt

# bcrypt only looks at the first 72 BYTES of a password. Longer passwords used to be
# silently truncated, so we reject them instead.
MAX_PASSWORD_BYTES = 72

_dummy_hash: str | None = None


def hash_password(plain_password: str) -> str:
    data = plain_password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password is longer than {MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(data, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    data = plain_password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(data, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # malformed hash in the DB - fail closed
        return False


def burn_time() -> None:
    """Spend the same time as a real password check.

    Called when the username does not exist (or the account is locked), so an
    attacker cannot tell valid usernames apart by measuring the response time.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password-0")
    verify_password("wrong-password-attempt", _dummy_hash)


def validate_password_strength(password: str, min_length: int = 10) -> list[str]:
    """Return a list of problems (empty list = password is acceptable)."""
    problems = []
    if len(password) < min_length:
        problems.append(f"Password must be at least {min_length} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        problems.append(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long.")
    if not any(c.isalpha() for c in password):
        problems.append("Password must contain at least one letter.")
    if not any(c.isdigit() for c in password):
        problems.append("Password must contain at least one digit.")
    return problems
