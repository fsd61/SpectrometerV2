"""Control dock: live parameter sliders + peak readouts (milestone 4).

Sliders mutate the shared :class:`ui.live.LiveParams` in place; the capture
thread reads it each frame, so changes take effect on the next frame. The peak
table is refreshed per frame from :func:`ui.live.peak_readout_rows`.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.live import LiveParams, peak_readout_rows

_COLUMNS = ["#", "Position", "Intensity", "FWHM", "SNR"]

_SMOOTH_TIP = (
    "Savitzky–Golay smoothing polynomial order.\n"
    "Lower = heavier smoothing (removes noise but can broaden or flatten "
    "peaks); higher = lighter smoothing (preserves sharp peaks but keeps more "
    "noise). Smooth just enough that noise stops producing false peaks."
)
_DIST_TIP = (
    "Minimum separation between detected peaks, in pixels.\n"
    "Increase to stop one broad line (or a noisy top) registering as several "
    "peaks; decrease to resolve closely-spaced lines."
)
_THRESH_TIP = (
    "Peak-detection threshold, as a fraction (0–1) of the tallest peak.\n"
    "A maximum must rise above this to count as a peak. Raise it to ignore "
    "small noise peaks; lower it to catch weak lines."
)
_MEASURE_TIP = (
    "Measure each peak's FWHM (line width) and SNR via a Gaussian fit.\n"
    "Slightly more work per frame — turn off for maximum frame rate when a "
    "frame has many peaks (e.g. on a Raspberry Pi)."
)


class ControlDock(QtWidgets.QDockWidget):
    """Right-hand dock with live analysis controls and a peak readout table."""

    def __init__(self, params: LiveParams, parent=None, on_change=None):
        super().__init__("Controls", parent)
        self._params = params
        # Called after any control edits ``params`` so the window can keep menu
        # / toolbar / keyboard state in sync with the dock.
        self._on_change = on_change

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)

        form = QtWidgets.QFormLayout()
        self._smooth_lbl = QtWidgets.QLabel(str(params.savgol_order))
        self._smooth = self._slider(0, 15, params.savgol_order, self._on_smooth)
        form.addRow(self._field_label("Smoothing (order)", _SMOOTH_TIP),
                    self._row(self._smooth, self._smooth_lbl, _SMOOTH_TIP))

        self._dist_lbl = QtWidgets.QLabel(str(params.peak_min_dist))
        self._dist = self._slider(0, 100, params.peak_min_dist, self._on_dist)
        form.addRow(self._field_label("Peak min distance", _DIST_TIP),
                    self._row(self._dist, self._dist_lbl, _DIST_TIP))

        self._thr_lbl = QtWidgets.QLabel(f"{params.peak_thres:.2f}")
        self._thr = self._slider(0, 100, round(params.peak_thres * 100), self._on_thr)
        form.addRow(self._field_label("Threshold", _THRESH_TIP),
                    self._row(self._thr, self._thr_lbl, _THRESH_TIP))
        layout.addLayout(form)

        self._measure = QtWidgets.QCheckBox("Measure FWHM / SNR")
        self._measure.setChecked(params.measure)
        self._measure.setToolTip(_MEASURE_TIP)
        self._measure.setStatusTip(_MEASURE_TIP.replace("\n", " "))
        self._measure.toggled.connect(self._on_measure)
        layout.addWidget(self._measure)

        # Persistent help panel: updates on hover/focus of a control. More
        # reliable than tooltips, which depend on hover-hold timing.
        self._default_help = "Hover or focus a control above for a description."
        self._help = QtWidgets.QLabel(self._default_help)
        self._help.setWordWrap(True)
        self._help.setStyleSheet(
            "QLabel { color: palette(mid); padding: 6px;"
            " border: 1px solid palette(midlight); border-radius: 4px; }"
        )
        self._help.setMinimumHeight(64)
        self._help.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self._help)

        # Register each control so hover/focus fills the help panel.
        self._help_text = {
            self._smooth: _SMOOTH_TIP, self._dist: _DIST_TIP,
            self._thr: _THRESH_TIP, self._measure: _MEASURE_TIP,
        }
        for widget in self._help_text:
            widget.installEventFilter(self)

        self._table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        self.setWidget(body)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _field_label(text, tip):
        lbl = QtWidgets.QLabel(text)
        lbl.setToolTip(tip)
        lbl.setStatusTip(tip.replace("\n", " "))
        return lbl

    @staticmethod
    def _slider(lo, hi, value, handler):
        s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.valueChanged.connect(handler)
        return s

    @staticmethod
    def _row(slider, label, tip=None):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        label.setMinimumWidth(36)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(label)
        if tip:
            slider.setToolTip(tip)
            slider.setStatusTip(tip.replace("\n", " "))
        return w

    def _on_smooth(self, v):
        self._params.savgol_order = int(v)
        self._smooth_lbl.setText(str(v))
        self._notify()

    def _on_dist(self, v):
        self._params.peak_min_dist = int(v)
        self._dist_lbl.setText(str(v))
        self._notify()

    def _on_thr(self, v):
        self._params.peak_thres = round(v / 100.0, 4)
        self._thr_lbl.setText(f"{self._params.peak_thres:.2f}")
        self._notify()

    def _on_measure(self, checked):
        self._params.toggle_measure() if bool(checked) != self._params.measure else None
        self._notify()

    def _notify(self):
        if self._on_change is not None:
            self._on_change()

    def sync_from_params(self) -> None:
        """Refresh every control from ``params`` (after a keyboard/menu change).

        Signals are blocked so writing widget values does not re-enter the
        handlers and clobber the params we are mirroring.
        """
        widgets = (self._smooth, self._dist, self._thr, self._measure)
        for widget in widgets:
            widget.blockSignals(True)
        self._smooth.setValue(int(self._params.savgol_order))
        self._dist.setValue(int(self._params.peak_min_dist))
        self._thr.setValue(int(round(self._params.peak_thres * 100)))
        self._measure.setChecked(bool(self._params.measure))
        for widget in widgets:
            widget.blockSignals(False)
        self._smooth_lbl.setText(str(self._params.savgol_order))
        self._dist_lbl.setText(str(self._params.peak_min_dist))
        self._thr_lbl.setText(f"{self._params.peak_thres:.2f}")

    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        etype = event.type()
        if etype in (
            QtCore.QEvent.Type.Enter,
            QtCore.QEvent.Type.FocusIn,
            QtCore.QEvent.Type.HoverEnter,
        ) and obj in self._help_text:
            self._help.setText(self._help_text[obj])
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    def update_readouts(self, spectrum, result) -> None:
        rows = peak_readout_rows(spectrum, result, force_pixel=self._params.pixel_mode)
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
