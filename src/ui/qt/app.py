"""PySide6 application bootstrap (Migration Plan Phase 7).

``run_gui`` builds the QApplication and main window and enters the Qt event
loop. It is imported lazily by ``app.commands.gui`` so the rest of the CLI works
without the optional ``[gui]`` extra installed.

**Startup ordering matters here.** Importing :mod:`ui.qt.main_window` pulls in
pyqtgraph, whose package ``__init__`` eagerly imports its entire API surface
(parametertree, imageview, multiprocessing, ...) and costs ~0.55 s on Windows —
over half of this application's total import time. Only ``PySide6.QtWidgets`` is
needed to put pixels on screen, so this module imports Qt at module scope, shows
a splash screen, and *then* imports the main window. That does not make startup
faster; it makes it visible, which is the part the user actually feels.
"""

from __future__ import annotations

import logging
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

# Mirrors the guidance in app.commands.gui; repeated here because the pyqtgraph
# import is now deferred past that module's try/except.
_GUI_EXTRA_HINT = (
    "The interactive GUI requires the [gui] extra (PySide6 + pyqtgraph), "
    "which is not installed.\nInstall it with 'pip install -e .[gui]'."
)

_SPLASH_SIZE = (460, 180)
_SPLASH_BG = QtGui.QColor(0x12, 0x16, 0x1B)
_SPLASH_FG = QtGui.QColor(0xE6, 0xE9, 0xEC)
_SPLASH_DIM = QtGui.QColor(0x8A, 0x93, 0x9D)


def _build_splash() -> QtWidgets.QSplashScreen:
    """A dependency-free splash screen drawn with QPainter.

    Deliberately not an image asset: loading one would mean touching the image
    plugins before the window exists, which is the cost this is trying to hide.
    """
    width, height = _SPLASH_SIZE
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(_SPLASH_BG)

    painter = QtGui.QPainter(pixmap)
    try:
        title_font = painter.font()
        title_font.setPointSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(_SPLASH_FG)
        painter.drawText(
            QtCore.QRect(28, 40, width - 56, 40),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "SpectrometerV2",
        )

        subtitle_font = painter.font()
        subtitle_font.setPointSize(9)
        subtitle_font.setBold(False)
        painter.setFont(subtitle_font)
        painter.setPen(_SPLASH_DIM)
        painter.drawText(
            QtCore.QRect(30, 78, width - 60, 20),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "Scientific spectrometer",
        )
    finally:
        painter.end()

    return QtWidgets.QSplashScreen(pixmap)


def _progress(app: QtWidgets.QApplication,
              splash: QtWidgets.QSplashScreen | None, message: str) -> None:
    """Paint a status line on the splash, if one is showing."""
    if splash is None:
        return
    splash.showMessage(
        f"  {message}",
        QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignLeft,
        _SPLASH_DIM,
    )
    app.processEvents()


def run_gui(config=None, logger: logging.Logger | None = None, *,
            splash: bool = True) -> int:
    """Launch the interactive GUI. Returns the Qt event-loop exit code.

    ``splash=False`` skips the splash screen (used by tests and by any caller
    embedding the window in an existing QApplication).
    """
    logger = logger or logging.getLogger(__name__)
    started = time.perf_counter()

    existing = QtWidgets.QApplication.instance()
    app = existing or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("SpectrometerV2")

    # Don't hijack an application someone else already built (tests, embedding).
    screen = _build_splash() if (splash and existing is None) else None
    if screen is not None:
        screen.show()
        _progress(app, screen, "Loading plotting engine…")

    try:
        # Deferred on purpose: this is the expensive pyqtgraph import (PLC0415).
        from .main_window import MainWindow
    except ImportError as exc:
        if screen is not None:
            screen.close()
        logger.error("GUI unavailable: %s", exc)
        print(_GUI_EXTRA_HINT, file=sys.stderr)
        return 1

    _progress(app, screen, "Building the window…")

    window = MainWindow(config=config, logger=logger)
    window.show()
    if screen is not None:
        screen.finish(window)

    logger.info("SpectrometerV2 GUI started (%.2f s from Qt bootstrap to first paint).",
                time.perf_counter() - started)
    return int(app.exec())
