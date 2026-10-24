"""
config.py
Centralized, environment-based configuration.
Never hardcode secrets in source files - everything sensitive is read
from environment variables (populated from a local .env file that is
NOT committed to version control; see .env.example).
"""

import os

from dotenv import load_dotenv

load_dotenv()  # loads variables from a .env file in the project root, if present


def _require(name: str) -> str:
    """Fetch a required environment variable or fail fast with a clear error."""
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill in real values."
        )
    return value


def _get_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"Environment variable '{name}' must be an integer, got {raw!r}.")
    if minimum is not None and value < minimum:
        raise RuntimeError(f"Environment variable '{name}' must be >= {minimum}, got {value}.")
    return value


def _get_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"Environment variable '{name}' must be a number, got {raw!r}.")
    if not (minimum < value <= maximum):
        raise RuntimeError(f"Environment variable '{name}' must be > {minimum} and <= {maximum}, got {value}.")
    return value


class Config:
    # --- Database ---
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = _get_int("DB_PORT", 3306, minimum=1)
    DB_USER = _require("DB_USER")
    DB_PASSWORD = _require("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME", "lms_database")

    # Connection pool sizing
    DB_POOL_NAME = os.getenv("DB_POOL_NAME", "lms_pool")
    DB_POOL_SIZE = _get_int("DB_POOL_SIZE", 5, minimum=1)

    # --- App ---
    APP_ENV = os.getenv("APP_ENV", "development")  # development | production
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    PAGE_SIZE = _get_int("PAGE_SIZE", 25, minimum=5)
    # How long lookup/report queries are cached (seconds). Every write clears the cache.
    CACHE_TTL_SECONDS = _get_int("CACHE_TTL_SECONDS", 30, minimum=1)

    # --- Auth ---
    # Session auto-expires after this many minutes of inactivity.
    SESSION_TIMEOUT_MINUTES = _get_int("SESSION_TIMEOUT_MINUTES", 30, minimum=1)
    # Lock an account after this many consecutive failed login attempts.
    MAX_LOGIN_ATTEMPTS = _get_int("MAX_LOGIN_ATTEMPTS", 5, minimum=1)
    LOGIN_LOCKOUT_MINUTES = _get_int("LOGIN_LOCKOUT_MINUTES", 15, minimum=1)
    PASSWORD_MIN_LENGTH = _get_int("PASSWORD_MIN_LENGTH", 10, minimum=8)

    # --- Grading scheme (the three maxima add up to the course total) ---
    # Defaults: assignments 20 + quizzes 20 + final exam 60 = 100 marks.
    GRADE_MAX_ASSIGNMENT = _get_float("GRADE_MAX_ASSIGNMENT", 20.0, 0, 100)
    GRADE_MAX_QUIZ = _get_float("GRADE_MAX_QUIZ", 20.0, 0, 100)
    GRADE_MAX_FINAL = _get_float("GRADE_MAX_FINAL", 60.0, 0, 100)

    @property
    def GRADE_TOTAL_MAX(self) -> float:
        return self.GRADE_MAX_ASSIGNMENT + self.GRADE_MAX_QUIZ + self.GRADE_MAX_FINAL

    @property
    def db_config(self) -> dict:
        return {
            "host": self.DB_HOST,
            "port": self.DB_PORT,
            "user": self.DB_USER,
            "password": self.DB_PASSWORD,
            "database": self.DB_NAME,
        }

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


config = Config()
