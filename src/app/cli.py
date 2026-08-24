"""Command-line interface definition (CLI-001..CLI-004).

Global options are accepted **on either side of the subcommand**. Argparse's
natural arrangement allows them only before it, which is backwards from how they
read — ``--frames`` applies solely to ``stream``, ``--plot`` solely to the
commands that render — so ``spectrometerv2 stream --frames 60`` is what most
people type first, and the "unrecognized arguments" error that follows says
nothing about ordering.

Two argparse behaviours shape the implementation:

* A subparser parses into a *fresh* namespace and copies the result over the
  outer one, so any option carrying an ordinary default would overwrite a value
  the caller supplied before the command. The subcommand copies therefore
  declare ``argparse.SUPPRESS``: an absent option contributes nothing.
* ``parents=[...]`` shares *Action objects* rather than copying them, and
  ``set_defaults`` mutates ``action.default`` in place. Using both together
  would push the top-level defaults onto the subcommand copies and reintroduce
  the clobbering. The options are therefore declared from one spec table and
  added twice, with different defaults, rather than shared.

The *accumulating* options — ``--set`` (append) and ``-v`` (count) — must
**merge** across the two sides rather than one replacing the other. Their
subcommand copies collect into private dests that :func:`parse_args` folds back
in; every other option simply takes whichever side supplied it.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from . import __version__

#: Prefix for the private dests the subcommand copies of accumulating options
#: write into, before :func:`parse_args` merges them into the real dest.
_AFTER = "_after_"

#: dest -> how to combine (before, after) when both sides supplied the option.
_ACCUMULATING = {
    "overrides": lambda before, after: list(before or []) + list(after or []),
    "verbose": lambda before, after: (before or 0) + (after or 0),
}

#: (name, help) for every subcommand.
COMMANDS = (
    ("run", "Acquire one spectrum, analyze, and save (default)."),
    ("validate-config", "Validate configuration and exit (CLI-004)."),
    ("describe-config", "Print the documented configuration schema."),
    ("init-config", "Write a documented config.ini (default: ~/.config/spectrometerv2/config.ini)."),
    ("test-camera", "Diagnostic: open the camera and grab a frame (CLI-004)."),
    ("verify-hardware", "Diagnostic: verify hardware (CLI-004)."),
    ("check-calibration", "Diagnostic: check wavelength calibration (CLI-004)."),
    ("generate-synthetic", "Generate synthetic spectral test data, analyze, and save (CLI-004, SYN-001)."),
    ("analyze", "Analyze a saved spectrum CSV (use --input) (CLI-004)."),
    ("stream", "Play a time-varying synthetic stream and render a waterfall PNG."),
    ("gui", "Launch the interactive GUI (needs the [gui] extra)."),
)

#: flags, argparse kwargs, top-level default. Added once per parser.
_OPTIONS = (
    (("--config",), {"metavar": "PATH",
                     "help": "Path to an INI configuration file (CLI-002)."}, None),
    (("-v", "--verbose"), {"action": "count",
                           "help": "Increase log verbosity; repeatable (-vv for DEBUG) (CLI-003)."}, 0),
    (("--set",), {"dest": "overrides", "action": "append", "metavar": "SECTION.KEY=VALUE",
                  "help": "Override a configuration value without editing the file "
                          "(CFG-006). Repeatable, and valid on either side of the command."}, None),
    (("-o", "--output"), {"metavar": "DIR",
                          "help": "Directory for saved outputs (default: current directory)."}, "."),
    (("-i", "--input"), {"metavar": "PATH",
                         "help": "Input spectrum CSV (for the 'analyze' command)."}, None),
    (("--force",), {"action": "store_true",
                    "help": "Overwrite an existing file (used by init-config)."}, False),
    (("--plot",), {"action": "store_true",
                   "help": "Also save a PNG plot of the spectrum (needs the [plot] extra)."}, False),
    (("--frames",), {"type": int, "metavar": "N",
                     "help": "Number of frames for the 'stream' command (default: 30)."}, 30),
)


def _add_common(parser: argparse.ArgumentParser, *, top_level: bool) -> None:
    """Attach the shared options.

    ``top_level`` selects real defaults; the subcommand copies suppress theirs so
    they cannot overwrite a value given before the command.
    """
    for flags, kwargs, default in _OPTIONS:
        options = dict(kwargs)
        if top_level:
            # A fresh list per parser: a module-level default would accumulate
            # --set values across repeated in-process invocations.
            options["default"] = [] if options.get("dest") == "overrides" else default
        else:
            options["default"] = argparse.SUPPRESS
            dest = options.get("dest") or flags[-1].lstrip("-").replace("-", "_")
            if dest in _ACCUMULATING:
                options["dest"] = _AFTER + dest
        parser.add_argument(*flags, **options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectrometerv2",
        description="SpectrometerV2 — cross-platform scientific spectrometer.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_common(parser, top_level=True)

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, description in COMMANDS:
        subparser = sub.add_parser(name, help=description)
        _add_common(subparser, top_level=False)

    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse ``argv``, merging options given on both sides of the subcommand."""
    args = build_parser().parse_args(argv)
    for dest, combine in _ACCUMULATING.items():
        private = _AFTER + dest
        trailing = getattr(args, private, None)
        if trailing:
            setattr(args, dest, combine(getattr(args, dest, None), trailing))
        if hasattr(args, private):
            delattr(args, private)
    return args
