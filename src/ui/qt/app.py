"""PySide6 application bootstrap (Migration Plan Phase 7).

``run_gui`` builds the QApplication and main window and enters the Qt event
loop. It is imported lazily by ``app.commands.gui`` so the rest of the CLI works
without the optional ``[gui]`` extra installed.
"""

from __future__ import annotations

import logging
import sys

from PySide6 import QtWidgets

from .main_window import MainWindow


def run_gui(config=None, logger: logging.Logger | None = None) -> int:
    """Launch the interactive GUI. Returns the Qt event-loop exit code."""
    logger = logger or logging.getLogger(__name__)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    window = MainWindow(config=config, logger=logger)
    window.show()
    logger.info("SpectrometerV2 GUI started.")
    return int(app.exec())
