"""Command-line interface definition (CLI-001..CLI-004)."""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectrometerv2",
        description="SpectrometerV2 — cross-platform scientific spectrometer.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

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
    parser.add_argument("-o", "--output", default=".", metavar="DIR",
                        help="Directory for saved outputs (default: current directory).")
    parser.add_argument("-i", "--input", metavar="PATH",
                        help="Input spectrum CSV (for the 'analyze' command).")
    parser.add_argument("--plot", action="store_true",
                        help="Also save a PNG plot of the spectrum (needs the [plot] extra).")
    parser.add_argument("--frames", type=int, default=30, metavar="N",
                        help="Number of frames for the 'stream' command (default: 30).")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("run", help="Acquire one spectrum, analyze, and save (default).")
    sub.add_parser("validate-config", help="Validate configuration and exit (CLI-004).")
    sub.add_parser("describe-config", help="Print the documented configuration schema.")
    sub.add_parser("test-camera", help="Diagnostic: open the camera and grab a frame (CLI-004).")
    sub.add_parser("verify-hardware", help="Diagnostic: verify hardware (CLI-004).")
    sub.add_parser("check-calibration", help="Diagnostic: check wavelength calibration (CLI-004).")
    sub.add_parser("generate-synthetic", help="Generate synthetic spectral test data, analyze, and save (CLI-004, SYN-001).")
    sub.add_parser("analyze", help="Analyze a saved spectrum CSV (use --input) (CLI-004).")
    sub.add_parser("stream", help="Play a time-varying synthetic stream and render a waterfall PNG.")

    return parser
