"""Live waterfall widget (Migration Plan Phase 7, milestone 3).

A scrolling 2-D image of recent spectra (rows = time, newest at top) rendered
with pyqtgraph. History, flooring, and the display levels live in the Qt-free
:class:`ui.live.WaterfallBuffer`; the nm scale comes from :mod:`ui.graticule`.
This widget only paints them.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6 import QtWidgets

from ui.graticule import marks as graticule_marks
from ui.live import WaterfallBuffer

# Match the PNG renderer's colormap for a consistent look.
pg.setConfigOption("imageAxisOrder", "row-major")

DEFAULT_COLORMAP = "inferno"


def _load_colormap(name: str):
    """Fetch a pyqtgraph colormap by name, falling back through its sources.

    Returns None if the name is unknown everywhere, in which case the caller
    keeps pyqtgraph's default LUT - a missing colormap is a cosmetic problem and
    must not stop the live view from painting.
    """
    for kwargs in ({}, {"source": "matplotlib"}):
        try:
            cmap = pg.colormap.get(name, **kwargs)
        except Exception:  # noqa: BLE001 - probing optional colormap sources
            continue
        if cmap is not None:
            return cmap
    return None


class WaterfallView(QtWidgets.QWidget):
    """Scrolling intensity image of the most recent spectra."""

    def __init__(self, frames: int = 256, full_scale=None,
                 colormap: str = DEFAULT_COLORMAP, use_smoothed: bool = False,
                 parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._buffer = WaterfallBuffer(height=frames, full_scale=full_scale)
        # Which trace is recorded. Raw by default, matching the original tool:
        # the waterfall's job is to show whether a feature persists across rows,
        # and persistence *is* the noise rejection. Smoothing first pre-empts
        # that judgement and attenuates narrow lines.
        self._use_smoothed = bool(use_smoothed)
        self._applied_ticks = None   # last tick list pushed to the axis
        self._calibrated = None      # last axis-label state

        self._widget = pg.GraphicsLayoutWidget()
        self._plot = self._widget.addPlot()
        self._plot.setLabel("left", "Frames ago")
        self._plot.setLabel("bottom", "Pixel")
        self._plot.invertY(True)     # row 0 (newest) at the top
        self._plot.setDefaultPadding(0.0)
        self._axis = self._plot.getAxis("bottom")

        self._image = pg.ImageItem()
        cmap = _load_colormap(colormap)
        if cmap is not None:
            self._image.setColorMap(cmap)
        self._plot.addItem(self._image)

        layout.addWidget(self._widget)

    def update_spectrum(self, spectrum, result) -> None:
        """Push a frame's intensities and repaint."""
        row = result.smoothed if self._use_smoothed else spectrum.intensities
        self._buffer.push(row)
        image = self._buffer.image()
        if image is None:
            return
        # Explicit levels, never autoLevels - see WaterfallBuffer.levels().
        self._image.setImage(image, levels=self._buffer.levels(), autoLevels=False)
        self._apply_scale(spectrum)

    def _apply_scale(self, spectrum) -> None:
        """Label the x axis in nm where calibrated, else in pixels.

        An uncalibrated frame gets pixel ticks, not a stale nm axis: serving a
        wavelength scale the current frame cannot justify is the same silent
        bad-data failure the calibration record guards against.
        """
        calibrated = len(spectrum.wavelengths) > 0
        if calibrated != self._calibrated:
            self._plot.setLabel("bottom", "Wavelength (nm)" if calibrated else "Pixel")
            self._calibrated = calibrated

        if not calibrated:
            if self._applied_ticks is not None:
                self._axis.setTicks(None)      # back to pyqtgraph's auto ticks
                self._applied_ticks = None
            return

        # Marks are pixel positions of whole 10/50 nm on the real (polynomial)
        # axis. +0.5 centres the tick in the pixel's cell, since an ImageItem
        # column spans [i, i+1).
        major = [(p + 0.5, f"{nm}nm") for p, nm in graticule_marks(spectrum.wavelengths, 50)]
        minor = [(p + 0.5, "") for p, _nm in graticule_marks(spectrum.wavelengths, 10)]
        ticks = [major, minor]
        # Recomputing every frame is cheap; repainting the axis is not, so only
        # push when the marks actually moved (i.e. on a recalibration).
        if ticks != self._applied_ticks:
            self._axis.setTicks(ticks)
            self._applied_ticks = ticks

    def clear(self) -> None:
        self._buffer.clear()
        self._image.clear()
        self._axis.setTicks(None)
        self._applied_ticks = None
        self._calibrated = None
