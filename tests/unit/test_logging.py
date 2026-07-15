"""Unit tests for the logging service (LOG-001, LOG-002)."""

import logging

from pyspectrometer2.logging_setup import setup_logging


def test_setup_creates_log_dir_and_handlers(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logging(level="DEBUG", directory=log_dir, console=False)
    assert log_dir.is_dir()
    assert logger.level == logging.DEBUG
    assert any(
        h.__class__.__name__ == "RotatingFileHandler" for h in logger.handlers
    )


def test_logging_writes_to_file(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logging(level="INFO", directory=log_dir, console=False)
    logger.info("hello regression")
    for h in logger.handlers:
        h.flush()
    log_file = log_dir / "pyspectrometer2.log"
    assert log_file.exists()
    assert "hello regression" in log_file.read_text(encoding="utf-8")


def test_setup_is_idempotent(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(directory=log_dir, console=False)
    logger = setup_logging(directory=log_dir, console=False)
    # No duplicate handler accumulation on repeated setup.
    assert len(logger.handlers) == 1
