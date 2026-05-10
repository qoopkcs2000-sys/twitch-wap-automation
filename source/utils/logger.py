"""Lightweight logger factory.

Each module asks for its own logger via ``get_logger(__name__)``. The
configuration is applied only once on import to avoid duplicate handlers
when fixtures/page objects are imported in different orders.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config.settings import Settings

_LOG_FORMAT = "%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    """Attach console + rotating file handler to the root logger once."""
    global _configured
    if _configured:
        return

    Settings.ensure_dirs()
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        Settings.LOGS_DIR / "test_run.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Selenium is too chatty at INFO; silence it.
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger."""
    _configure_root()
    return logging.getLogger(name)
