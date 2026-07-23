"""Live spectrum plot widget (Migration Plan Phase 7, milestone 2).

A pyqtgraph line plot of the (smoothed) spectrum with peak markers. It renders
whatever the Qt-free ``LiveEngine`` produces; it holds no analysis logic itself.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

_TRACE_PEN = pg.mkPen("#1D9E75", width=2)
_PEAK_BRUSH = pg.mkBrush("#BA7517")
_PEAK_PEN = pg.mkPen("#7A4C0F")


class SpectrumView(QtWidgets.QWidget):
    """Intensity-vs-wavelength (or pixel) plot with peak markers."""

    # Emitted with the plot x-coordinate of a left-click (used by click-to-
    # calibrate; on the uncalibrated camera axis this x is a pixel index).
    plotClicked = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Intensity")
        self._plot.setLabel("bottom", "Wavelength", units="nm")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._curve = self._plot.plot([], [], pen=_TRACE_PEN)
        self._peaks = pg.ScatterPlotItem(size=9, pen=_PEAK_PEN, brush=_PEAK_BRUSH)
        self._plot.addItem(self._peaks)
        self._calibrated = None  # track axis label changes

        self._plot.scene().sigMouseClicked.connect(self._on_scene_click)
        layout.addWidget(self._plot)

    def _on_scene_click(self, event) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        vb = self._plot.getPlotItem().vb
        if not self._plot.sceneBoundingRect().contains(event.scenePos()):
            return
        point = vb.mapSceneToView(event.scenePos())
        self.plotClicked.emit(float(point.x()))

    def update_spectrum(self, spectrum, result) -> None:
        """Repaint from a (Spectrum, SpectralAnalysis) pair.

        The trace is floored at zero: a detector cannot report negative light, so
        Savitzky-Golay ringing at the foot of sharp lines is clamped away. Peak
        detection and measurements are unaffected (they run on the unclamped
        analysis result).
        """
        y = np.clip(np.asarray(result.smoothed, dtype=float), 0.0, None)
        calibrated = len(spectrum.wavelengths) > 0
        if calibrated:
            x = np.asarray(spectrum.wavelengths, dtype=float)
        else:
            x = np.arange(len(y), dtype=float)

        if calibrated != self._calibrated:
            self._plot.setLabel(
                "bottom", "Wavelength" if calibrated else "Pixel",
                units="nm" if calibrated else None,
            )
            self._calibrated = calibrated

        self._curve.setData(x, y)
        if result.peaks:
            px = [p.wavelength if p.wavelength is not None else p.pixel for p in result.peaks]
            py = [y[p.pixel] if p.pixel < len(y) else p.intensity for p in result.peaks]
            self._peaks.setData(px, py)
        else:
            self._peaks.setData([], [])
