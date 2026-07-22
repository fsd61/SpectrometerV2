"""Live waterfall widget (Migration Plan Phase 7, milestone 3).

A scrolling 2-D image of recent spectra (rows = time, newest at top) rendered
with pyqtgraph. History and flooring live in the Qt-free
:class:`ui.live.WaterfallBuffer`; this widget only paints it.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from ui.live import WaterfallBuffer

# Match the PNG renderer's colormap for a consistent look.
pg.setConfigOption("imageAxisOrder", "row-major")


class WaterfallView(QtWidgets.QWidget):
    """Scrolling intensity image of the most recent spectra."""

    def __init__(self, frames: int = 256, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._buffer = WaterfallBuffer(height=frames)

        self._widget = pg.GraphicsLayoutWidget()
        view = self._widget.addViewBox()
        view.setAspectLocked(False)
        view.invertY(True)  # row 0 (newest) at the top
        self._image = pg.ImageItem()
        try:
            self._image.setColorMap(pg.colormap.get("viridis"))
        except Exception:  # noqa: BLE001 - colormap optional; default LUT is fine
            pass
        view.addItem(self._image)
        self._view = view

        layout.addWidget(self._widget)

    def update_spectrum(self, spectrum, result) -> None:
        """Push a frame's smoothed intensities and repaint."""
        self._buffer.push(result.smoothed)
        image = self._buffer.image()
        if image is not None:
            self._image.setImage(image, autoLevels=True)

    def clear(self) -> None:
        self._buffer.clear()
        self._image.clear()
