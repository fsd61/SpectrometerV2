"""Capture thread for the live view (Migration Plan Phase 7, milestone 2).

Runs the Qt-free :class:`ui.live.LiveEngine` off the UI thread so frame capture
and analysis never block the window. Finished frames are delivered to the UI via
a Qt signal; the widgets repaint on the UI thread.
"""

from __future__ import annotations

import time

from PySide6 import QtCore

from ui.live import LiveEngine


class CaptureThread(QtCore.QThread):
    """Repeatedly steps a ``LiveEngine`` and emits each analyzed frame."""

    frameReady = QtCore.Signal(object, object)  # (Spectrum, SpectralAnalysis)
    error = QtCore.Signal(str)

    def __init__(self, engine: LiveEngine, fps: float = 15.0, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._interval = 1.0 / max(1e-3, fps)
        self._running = True

    def run(self) -> None:  # executes on the worker thread
        while self._running:
            start = time.monotonic()
            try:
                spectrum, result = self._engine.step()
            except Exception as exc:  # noqa: BLE001 - surface to UI, don't crash
                self.error.emit(str(exc))
                break
            self.frameReady.emit(spectrum, result)
            remaining = self._interval - (time.monotonic() - start)
            if remaining > 0:
                self.msleep(int(remaining * 1000))

    def stop(self) -> None:
        """Stop the loop, wait for it to finish, and release the engine."""
        self._running = False
        self.wait(2000)
        self._engine.close()
