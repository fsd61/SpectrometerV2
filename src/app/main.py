"""Application entry point: parse args, configure services, dispatch (ERR-002)."""

from __future__ import annotations

import logging
import sys
from typing import Optional, Sequence

from config import load_config, discover_config_path
from config.schema import SCHEMA
from errors import ConfigError, PySpectrometerError
from logging_setup import setup_logging
from . import commands
from .cli import build_parser

_VERBOSITY = ["INFO", "DEBUG"]

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "describe-config":
        _describe_config()
        return 0
    if args.command == "init-config":
        return commands.init_config(args.output, args.force)

    try:
        config = load_config(config_path=args.config or discover_config_path(), overrides=args.overrides)
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2

    log_cfg = config.section("logging")
    level = _VERBOSITY[min(args.verbose, len(_VERBOSITY) - 1)] if args.verbose else log_cfg["level"]
    logger = setup_logging(
        level=level, directory=log_cfg["directory"], max_bytes=log_cfg["max_bytes"],
        backup_count=log_cfg["backup_count"], console=log_cfg["console"],
    )

    command = args.command or "run"
    try:
        return _dispatch(command, config, logger, args)
    except PySpectrometerError as exc:
        logger.error("%s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - last-resort guard: log before exit (ERR-002)
        logger.exception("Unexpected fatal error")
        return 1


def _dispatch(command: str, config, logger: logging.Logger, args) -> int:
    if command == "validate-config":
        logger.info("Configuration is valid.")
        print("Configuration is valid.")
        return 0
    if command == "run":
        return commands.run(config, logger, args.output, args.plot)
    if command == "test-camera":
        return commands.test_camera(config, logger)
    if command == "generate-synthetic":
        return commands.generate_synthetic(config, logger, args.output, args.plot)
    if command == "analyze":
        return commands.analyze_file(config, logger, args.input, args.plot)
    if command == "verify-hardware":
        return commands.verify_hardware(config, logger)
    if command == "check-calibration":
        return commands.check_calibration(config, logger)
    if command == "stream":
        return commands.stream(config, logger, args.output, args.frames)
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
