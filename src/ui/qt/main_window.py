"""Main application window (Migration Plan Phase 7).

Milestone 2: hosts the live spectrum plot and drives a capture thread over the
active frame source (synthetic by default). Later milestones add the waterfall,
control dock, menu/toolbar, and click-to-calibrate.
"""

from __future__ import annotations

import logging

from PySide6 import QtWidgets

from PySide6 import QtCore

from ui.live import LiveEngine, LiveParams, build_frame_source
from .controller import CaptureThread
from .controls import ControlDock
from .spectrum_view import SpectrumView
from .waterfall_view import WaterfallView


class MainWindow(QtWidgets.QMainWindow):
    """The top-level SpectrometerV2 window."""

    def __init__(self, config=None, logger=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        self.setWindowTitle("SpectrometerV2")
        self.resize(1100, 700)

        frames = 256
        if config is not None:
            frames = int(config.section("gui").get("waterfall_frames", 256))

        self._params = LiveParams(measure=True)

        self._view = SpectrumView()
        self._waterfall = WaterfallView(frames=frames)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self._view)
        splitter.addWidget(self._waterfall)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._dock = ControlDock(self._params)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._dock)

        self._thread: CaptureThread | None = None
        self._start_capture()

    # ------------------------------------------------------------------ #
    def _start_capture(self) -> None:
        if self.config is None:
            self.statusBar().showMessage("No configuration — idle")
            return
        try:
            source = build_frame_source(self.config, self.logger)
        except Exception as exc:  # noqa: BLE001 - report, keep window alive
            self.statusBar().showMessage(f"Could not start capture: {exc}")
            self.logger.error("Could not start capture: %s", exc)
            return

        engine = LiveEngine(source, self._params)
        fps = float(self.config.section("gui").get("fps", 15.0))
        self._thread = CaptureThread(engine, fps=fps)
        self._thread.frameReady.connect(self._on_frame)
        self._thread.error.connect(self._on_error)
        self._thread.start()
        self.statusBar().showMessage("Live")

    def _on_frame(self, spectrum, result) -> None:
        self._view.update_spectrum(spectrum, result)
        self._waterfall.update_spectrum(spectrum, result)
        self._dock.update_readouts(spectrum, result)
        self.statusBar().showMessage(
            f"Live — {len(spectrum)} samples, {len(result.peaks)} peaks"
        )

    def _on_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Capture stopped: {message}")
        self.logger.error("Capture error: %s", message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._thread is not None:
            self._thread.stop()
            self._thread = None
        super().closeEvent(event)
