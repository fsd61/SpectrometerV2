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


class TaskWorker(QtCore.QThread):
    """Runs one slow, Qt-free computation (a line fit, a centroid comparison)
    off the UI thread so the live view keeps updating.

    ``fn`` is called as ``fn(progress, should_stop)``: ``progress(i, n)``
    reports progress and ``should_stop()`` returns True once :meth:`cancel` has
    been called. The result, or the error message, is delivered by signal.
    """

    progress = QtCore.Signal(int, int)
    finished_ok = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # executes on the worker thread
        try:
            result = self._fn(lambda i, n: self.progress.emit(int(i), int(n)),
                              lambda: self._cancelled)
        except Exception as exc:  # noqa: BLE001 - surface to UI, don't crash
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)
