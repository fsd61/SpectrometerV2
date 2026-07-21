"""Tests for the `gui` subcommand: parsing and graceful fallback.

These do not launch a window. The fallback test forces PySide6 to be
unimportable so it verifies the actionable message on *any* machine, whether or
not the [gui] extra is installed.
"""

import logging
import sys

from app import commands
from app.cli import build_parser


def test_parser_accepts_gui_subcommand():
    args = build_parser().parse_args(["gui"])
    assert args.command == "gui"


def test_gui_falls_back_without_pyside6(monkeypatch, capsys):
    # Make `import PySide6` raise ImportError regardless of the environment.
    monkeypatch.setitem(sys.modules, "PySide6", None)
    for cached in ("ui.qt.app", "ui.qt.main_window"):
        monkeypatch.delitem(sys.modules, cached, raising=False)

    rc = commands.gui(config=None, logger=logging.getLogger("test"))

    assert rc == 1
    err = capsys.readouterr().err
    assert "[gui]" in err and "pip install" in err
