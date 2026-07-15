"""Centralized logging service (LOG-001, LOG-002, ERR-002).

Provides structured application logging with a dedicated logs directory and
size-based rotation. All modules obtain loggers via ``logging.getLogger`` under
the ``spectrometerv2`` namespace; this module configures the handlers once at
startup.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

ROOT_LOGGER_NAME = "spectrometerv2"
LOG_FILENAME = "spectrometerv2.log"

# Structured, fixed-field format: timestamp, level, logger, message.
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(
    level: str = "INFO",
    directory: str | Path = "logs",
    max_bytes: int = 1_048_576,
    backup_count: int = 5,
    console: bool = True,
    logger_name: str = ROOT_LOGGER_NAME,
) -> logging.Logger:
    """Configure and return the application root logger.

    Args:
        level: Minimum level name (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        directory: Directory for rotating log files; created if absent (LOG-002).
        max_bytes: Rotate the log file once it exceeds this size.
        backup_count: Number of rotated files to retain.
        console: Also emit to stderr when True.
        logger_name: Namespace to configure.

    Returns:
        The configured ``logging.Logger``.
    """
    log_dir = Path(directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(_resolve_level(level))
    logger.handlers.clear()          # idempotent: safe to call more than once
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / LOG_FILENAME,
        maxBytes=int(max_bytes),
        backupCount=int(backup_count),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.debug(
        "Logging initialized (level=%s, dir=%s, max_bytes=%d, backups=%d)",
        level, log_dir, max_bytes, backup_count,
    )
    return logger


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelName(str(level).upper())
    return resolved if isinstance(resolved, int) else logging.INFO
