"""Command-line interface definition (CLI-001..CLI-004).

Builds the argument parser only; execution lives in ``main``. Diagnostic modes
required by CLI-004 are exposed as subcommands (camera testing, hardware
verification, calibration checks, configuration validation, synthetic-data
generation, and analysis).
"""

from __future__ import annotations

import argparse

from .. import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyspectrometer2",
        description="PySpectrometer2 — cross-platform scientific spectrometer.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # Global options (apply to every command).
    parser.add_argument("--config", metavar="PATH", help="Path to an INI configuration file (CLI-002).")
    parser.add_argument("--profile", metavar="NAME", help="Configuration profile to overlay (CLI-002, CFG-003).")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase log verbosity; repeatable (-vv for DEBUG) (CLI-003).",
    )
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE",
        help="Override a configuration value without editing the file (CFG-006). Repeatable.",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("run", help="Run acquisition and analysis (default).")
    sub.add_parser("validate-config", help="Validate configuration and exit (CLI-004).")
    sub.add_parser("describe-config", help="Print the documented configuration schema.")
    sub.add_parser("test-camera", help="Diagnostic: test camera connectivity (CLI-004).")
    sub.add_parser("verify-hardware", help="Diagnostic: verify hardware (CLI-004).")
    sub.add_parser("check-calibration", help="Diagnostic: check wavelength calibration (CLI-004).")
    sub.add_parser("generate-synthetic", help="Generate synthetic spectral test data (CLI-004, SYN-001).")
    sub.add_parser("analyze", help="Run scientific analysis on input data (CLI-004).")

    return parser
