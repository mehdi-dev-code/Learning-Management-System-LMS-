"""
logger.py
Central logging configuration. Errors go to ONE rotating file handler
attached to the parent "lms" logger, so every module shares it. (The old
version attached a separate handler per module to the same file, which
breaks log rotation.) Nothing here ever logs query parameters, so student
emails / phone numbers never end up in the log file.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config import config

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_ROOT_NAME = "lms"


def _configure_once() -> None:
    root = logging.getLogger(_ROOT_NAME)
    if root.handlers:
        # Already configured (Streamlit re-runs scripts on every interaction).
        return

    os.makedirs(config.LOG_DIR, exist_ok=True)
    root.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = RotatingFileHandler(
        os.path.join(config.LOG_DIR, "lms.log"),
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not config.is_production:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    _configure_once()
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
