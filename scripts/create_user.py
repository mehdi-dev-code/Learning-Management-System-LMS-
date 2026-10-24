"""
Create a user (or reset an existing user's password) from the command line.

    python scripts/create_user.py

Used to create the FIRST administrator. Afterwards administrators can manage users
inside the app (Account -> Users). Passwords are typed with getpass, so they are never
shown on screen or saved in shell history.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config  # noqa: E402
from db import DatabaseError, run_action, run_one  # noqa: E402
from security import hash_password, validate_password_strength  # noqa: E402
from utils.validators import USERNAME_RE  # noqa: E402


def main() -> int:
    username = input("Username: ").strip()
    if not USERNAME_RE.match(username):
        print("Username must be 3-50 characters: letters, digits, dot, dash or underscore.")
        return 1

    role = input("Role [admin/staff] (default: admin): ").strip().lower() or "admin"
    if role not in ("admin", "staff"):
        print("Role must be 'admin' or 'staff'.")
        return 1

    password = getpass.getpass("Password: ")
    problems = validate_password_strength(password, config.PASSWORD_MIN_LENGTH)
    if problems:
        print("\n".join(problems))
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        return 1

    try:
        existing = run_one("SELECT user_id FROM users WHERE username = %s", (username,))
        if existing:
            answer = input(f"User '{username}' already exists. Reset the password and unlock it? [y/N]: ")
            if answer.strip().lower() != "y":
                print("Nothing changed.")
                return 0
            run_action(
                "UPDATE users SET password_hash = %s, role = %s, is_active = 1, "
                "failed_attempts = 0, locked_until = NULL WHERE user_id = %s",
                (hash_password(password), role, existing["user_id"]),
            )
            print(f"Password reset for '{username}' (role: {role}).")
        else:
            run_action(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, hash_password(password), role),
            )
            print(f"User '{username}' created (role: {role}).")
    except DatabaseError as e:
        print(f"Database error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
