"""
Logger Configuration Module

Provides centralized logging for the application.
Call setup_logging() once at startup; use get_logger(__name__) everywhere else.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "."))
LOG_DIR.mkdir(exist_ok=True)

_FMT = "%(asctime)s %(name)-20s %(levelname)-8s %(message)s"
_DETAILED_FMT = "%(asctime)s %(name)s [%(filename)s:%(lineno)d] %(levelname)s: %(message)s"


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(level=level, format=_FMT)

    # File handler – all logs
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(_FMT))
    file_handler.setLevel(level)

    # Error-only file handler
    error_handler = RotatingFileHandler(
        LOG_DIR / "error.log", maxBytes=10 * 1024 * 1024, backupCount=3
    )
    error_handler.setFormatter(logging.Formatter(_DETAILED_FMT))
    error_handler.setLevel(logging.ERROR)

    root = logging.getLogger()
    root.addHandler(file_handler)
    root.addHandler(error_handler)

    # Silence noisy third-party libraries
    for noisy in ("pip", "urllib3", "werkzeug", "google.auth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {log_level}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module."""
    return logging.getLogger(name)


# Auto-configure when imported
if __name__ != "__main__":
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
