"""Application entry point: parse args, configure services, dispatch (ERR-002).

The whole run is wrapped so that any unexpected failure is logged before a
controlled, non-zero exit whenever logging is available, and configuration
errors terminate gracefully with a clear message (CFG-005).
"""

from __future__ import annotations

import logging
import sys
from typing import Optional, Sequence

from config import load_config
from config.schema import SCHEMA
from errors import ConfigError, PySpectrometerError
from logging_setup import setup_logging
from .cli import build_parser

_VERBOSITY = ["INFO", "DEBUG"]  # index by --verbose count (capped)

# Diagnostic/pipeline commands not yet implemented in the skeleton. They are
# recognized and dispatched, but report a clear "not yet implemented" status
# rather than crashing (supports incremental migration).
_NOT_YET_IMPLEMENTED = {
    "run": "acquisition/analysis pipeline",
    "test-camera": "camera connectivity diagnostic",
    "verify-hardware": "hardware verification diagnostic",
    "check-calibration": "calibration check diagnostic",
    "generate-synthetic": "synthetic data generation",
    "analyze": "analysis pipeline",
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 'describe-config' needs neither config nor logging; handle it first.
    if args.command == "describe-config":
        _describe_config()
        return 0

    # Load + validate configuration (CFG-005: graceful failure, clear message).
    try:
        config = load_config(
            config_path=args.config,
            profile=args.profile,
            overrides=args.overrides,
        )
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2

    # Configure logging from config, with CLI verbosity taking precedence (CLI-003).
    log_cfg = config.section("logging")
    level = _VERBOSITY[min(args.verbose, len(_VERBOSITY) - 1)] if args.verbose else log_cfg["level"]
    logger = setup_logging(
        level=level,
        directory=log_cfg["directory"],
        max_bytes=log_cfg["max_bytes"],
        backup_count=log_cfg["backup_count"],
        console=log_cfg["console"],
    )

    command = args.command or "run"
    try:
        return _dispatch(command, config, logger)
    except PySpectrometerError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:  # noqa: BLE001 - last-resort guard: log before exit (ERR-002)
        logger.exception("Unexpected fatal error")
        return 1


def _dispatch(command: str, config, logger: logging.Logger) -> int:
    if command == "validate-config":
        logger.info("Configuration is valid.")
        print("Configuration is valid.")
        return 0

    if command in _NOT_YET_IMPLEMENTED:
        logger.warning("Command '%s' (%s) is not yet implemented in this build.",
                       command, _NOT_YET_IMPLEMENTED[command])
        print(f"'{command}' is not yet implemented (skeleton build).", file=sys.stderr)
        return 0

    logger.error("Unknown command: %s", command)
    return 2


def _describe_config() -> None:
    """Render the documented schema (CFG-004)."""
    for section, keys in SCHEMA.items():
        print(f"[{section}]")
        for key, field in keys.items():
            bits = [f"type={field.type}", f"default={field.default!r}"]
            if field.choices is not None:
                bits.append(f"choices={list(field.choices)}")
            if field.min is not None:
                bits.append(f"min={field.min}")
            if field.max is not None:
                bits.append(f"max={field.max}")
            print(f"  {key}: {field.doc}")
            print(f"      ({', '.join(bits)})")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
