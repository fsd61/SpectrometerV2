"""Control dock: live parameter sliders + peak readouts (milestone 4).

Sliders mutate the shared :class:`ui.live.LiveParams` in place; the capture
thread reads it each frame, so changes take effect on the next frame. The peak
table is refreshed per frame from :func:`ui.live.peak_readout_rows`.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.live import LiveParams, peak_readout_rows

_COLUMNS = ["#", "Position", "Intensity", "FWHM", "SNR"]


class ControlDock(QtWidgets.QDockWidget):
    """Right-hand dock with live analysis controls and a peak readout table."""

    def __init__(self, params: LiveParams, parent=None):
        super().__init__("Controls", parent)
        self._params = params

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)

        form = QtWidgets.QFormLayout()
        self._smooth_lbl = QtWidgets.QLabel(str(params.savgol_order))
        self._smooth = self._slider(0, 15, params.savgol_order, self._on_smooth)
        form.addRow("Smoothing (order)", self._row(self._smooth, self._smooth_lbl))

        self._dist_lbl = QtWidgets.QLabel(str(params.peak_min_dist))
        self._dist = self._slider(0, 100, params.peak_min_dist, self._on_dist)
        form.addRow("Peak min distance", self._row(self._dist, self._dist_lbl))

        self._thr_lbl = QtWidgets.QLabel(f"{params.peak_thres:.2f}")
        self._thr = self._slider(0, 100, round(params.peak_thres * 100), self._on_thr)
        form.addRow("Threshold", self._row(self._thr, self._thr_lbl))
        layout.addLayout(form)

        self._measure = QtWidgets.QCheckBox("Measure FWHM / SNR")
        self._measure.setChecked(params.measure)
        self._measure.toggled.connect(self._on_measure)
        layout.addWidget(self._measure)

        self._table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        self.setWidget(body)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _slider(lo, hi, value, handler):
        s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.valueChanged.connect(handler)
        return s

    @staticmethod
    def _row(slider, label):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        label.setMinimumWidth(36)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(label)
        return w

    def _on_smooth(self, v):
        self._params.savgol_order = int(v)
        self._smooth_lbl.setText(str(v))

    def _on_dist(self, v):
        self._params.peak_min_dist = int(v)
        self._dist_lbl.setText(str(v))

    def _on_thr(self, v):
        self._params.peak_thres = round(v / 100.0, 4)
        self._thr_lbl.setText(f"{self._params.peak_thres:.2f}")

    def _on_measure(self, checked):
        self._params.measure = bool(checked)

    # ------------------------------------------------------------------ #
    def update_readouts(self, spectrum, result) -> None:
        rows = peak_readout_rows(spectrum, result)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            pos = f"{row.position:.1f} nm" if row.calibrated else f"px {int(row.position)}"
            fwhm = "—" if row.fwhm is None else (
                f"{row.fwhm:.2f} nm" if row.fwhm_calibrated else f"{row.fwhm:.1f} px"
            )
            snr = "—" if row.snr is None else f"{row.snr:.0f}"
            values = [str(row.index), pos, f"{row.intensity:.0f}", fwhm, snr]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QtWidgets.QTableWidgetItem(text))
