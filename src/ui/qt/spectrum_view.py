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
_RAW_PEN = pg.mkPen((150, 150, 150, 140), width=1)
_FIT_PEN = pg.mkPen("#D95926", width=2, style=QtCore.Qt.PenStyle.DashLine)
_COMPONENT_PEN = pg.mkPen("#3987E5", width=1, style=QtCore.Qt.PenStyle.DashLine)


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
        # Raw spectrum, drawn faintly behind the processed trace when a
        # denoising stage fed the analysis, so its effect is visible.
        self._raw = self._plot.plot([], [], pen=_RAW_PEN)
        self._show_raw = True
        self._curve = self._plot.plot([], [], pen=_TRACE_PEN)
        # Line-fit overlay: the total model and each fitted line.
        self._fit_model = self._plot.plot([], [], pen=_FIT_PEN)
        self._fit_components: list = []
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
        if getattr(result, "denoised", None) is not None and self._show_raw:
            raw = np.clip(np.asarray(spectrum.intensities, dtype=float), 0.0, None)
            self._raw.setData(x[: len(raw)], raw[: len(x)])
        else:
            self._raw.setData([], [])
        if result.peaks:
            px = [p.wavelength if p.wavelength is not None else p.pixel for p in result.peaks]
            py = [y[p.pixel] if p.pixel < len(y) else p.intensity for p in result.peaks]
            self._peaks.setData(px, py)
        else:
            self._peaks.setData([], [])

    # ------------------------------------------------------------------ #
    # Overlays
    # ------------------------------------------------------------------ #
    def set_raw_overlay(self, on: bool) -> None:
        self._show_raw = bool(on)
        if not on:
            self._raw.setData([], [])

    def show_fit(self, fit, wavelengths=None, samples_per_px: int = 8) -> None:
        """Draw a :class:`analysis.linefit.LineFitResult` over the spectrum.

        The fit lives in pixel space; on a calibrated axis it is mapped to nm
        through the wavelength axis that was current when the fit was made.
        """
        self.clear_fit()
        lo, hi = fit.window
        px = np.linspace(lo, hi - 1, max(2, (hi - lo) * samples_per_px))
        if wavelengths is not None and len(wavelengths) >= hi:
            x = np.interp(px, np.arange(len(wavelengths)), np.asarray(wavelengths, dtype=float))
        else:
            x = px
        self._fit_model.setData(x, fit.model(px))
        base = fit.baseline_at(px)
        for comp in fit.components(px):
            item = self._plot.plot(x, base + comp, pen=_COMPONENT_PEN)
            self._fit_components.append(item)

    def clear_fit(self) -> None:
        self._fit_model.setData([], [])
        for item in self._fit_components:
            self._plot.removeItem(item)
        self._fit_components = []

    def fit_item_count(self) -> int:
        """Number of drawn fit curves (model + components); for tests."""
        data = self._fit_model.getData()[0]
        drawn = 0 if data is None or len(data) == 0 else 1
        return drawn + len(self._fit_components)
