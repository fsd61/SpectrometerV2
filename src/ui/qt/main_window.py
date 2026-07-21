"""Main application window (Migration Plan Phase 7).

Milestone 1 is a skeleton: a titled window with a placeholder central widget and
a status bar. Later milestones add the spectrum plot, waterfall, control dock,
menu/toolbar, and click-to-calibrate.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class MainWindow(QtWidgets.QMainWindow):
    """The top-level SpectrometerV2 window."""

    def __init__(self, config=None, logger=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logger = logger

        self.setWindowTitle("SpectrometerV2")
        self.resize(1100, 700)

        placeholder = QtWidgets.QLabel(
            "SpectrometerV2\nLive view coming online…"
        )
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

        self.statusBar().showMessage("Ready")
