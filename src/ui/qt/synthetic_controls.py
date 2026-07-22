"""Synthetic-source control dock (Migration Plan Phase 7, milestone 4.5).

A live signal generator for **synthetic mode only**. Global controls (SNR,
baseline, sample interval, seed, wavelength range, drift) plus an add/remove peak
table (wavelength, amplitude, FWHM per line). Every edit rebuilds the
:class:`ui.live.SyntheticSpectrumSpec` and swaps it into the running
:class:`ui.live.SyntheticFrameSource`, so the live plot/waterfall/readouts update
on the next frame.

This is a simulator, never measured data — the window is marked ``[SIMULATED]``
while it is active, and this dock is only created when the backend is synthetic.
"""

from __future__ import annotations

from PySide6 import QtWidgets

from ui.live import (
    SyntheticFrameSource,
    SyntheticPeak,
    build_synthetic_spec,
    spec_to_peaks,
)

_PEAK_COLUMNS = ["Wavelength (nm)", "Amplitude", "FWHM (nm)"]


def _spin(lo, hi, value, decimals, step):
    box = QtWidgets.QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


class SyntheticDock(QtWidgets.QDockWidget):
    """Live editor for the synthetic signal driving the view."""

    def __init__(self, source: SyntheticFrameSource, parent=None):
        super().__init__("Synthetic source  [SIMULATED]", parent)
        self._source = source
        self._loading = True
        spec = source.spec

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)

        note = QtWidgets.QLabel("Simulated signal generator — not measured data.")
        note.setWordWrap(True)
        note.setStyleSheet("QLabel { color: palette(mid); font-style: italic; }")
        layout.addWidget(note)

        form = QtWidgets.QFormLayout()
        self._snr = _spin(0, 100000, spec.snr, 0, 10)
        self._baseline = _spin(-1000, 100000, spec.baseline, 1, 1)
        self._interval = _spin(0.01, 10, spec.sample_interval, 2, 0.1)
        self._wl_min = _spin(1, 10000, spec.wavelength_min, 1, 10)
        self._wl_max = _spin(1, 10000, spec.wavelength_max, 1, 10)
        self._seed = QtWidgets.QSpinBox()
        self._seed.setRange(0, 2_147_483_647)
        self._seed.setValue(int(spec.seed))
        self._drift = QtWidgets.QCheckBox("Drift peaks over time")
        self._drift.setChecked(source.stream.drift_nm > 0)

        form.addRow("SNR", self._snr)
        form.addRow("Baseline", self._baseline)
        form.addRow("Sample interval (nm)", self._interval)
        form.addRow("Wavelength min (nm)", self._wl_min)
        form.addRow("Wavelength max (nm)", self._wl_max)
        form.addRow("Seed", self._seed)
        form.addRow("", self._drift)
        layout.addLayout(form)

        for box in (self._snr, self._baseline, self._interval, self._wl_min, self._wl_max):
            box.valueChanged.connect(self._rebuild)
        self._seed.valueChanged.connect(self._rebuild)
        self._drift.toggled.connect(self._rebuild)

        self._table = QtWidgets.QTableWidget(0, len(_PEAK_COLUMNS))
        self._table.setHorizontalHeaderLabels(_PEAK_COLUMNS)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        buttons = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Add peak")
        add.clicked.connect(lambda: self._add_peak(SyntheticPeak(550.0, 100.0, 2.0)))
        remove = QtWidgets.QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        layout.addLayout(buttons)

        for peak in spec_to_peaks(spec):
            self._add_peak(peak)

        self.setWidget(body)
        self._loading = False

    # ------------------------------------------------------------------ #
    def _add_peak(self, peak: SyntheticPeak) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        cells = (
            _spin(1, 10000, peak.wavelength, 1, 1),
            _spin(0, 100000, peak.amplitude, 1, 5),
            _spin(0.1, 1000, peak.fwhm, 2, 0.5),
        )
        for c, box in enumerate(cells):
            box.valueChanged.connect(self._rebuild)
            self._table.setCellWidget(r, c, box)
        self._rebuild()

    def _remove_selected(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._rebuild()

    def _collect_peaks(self) -> list[SyntheticPeak]:
        peaks = []
        for r in range(self._table.rowCount()):
            w = self._table.cellWidget(r, 0).value()
            a = self._table.cellWidget(r, 1).value()
            f = self._table.cellWidget(r, 2).value()
            peaks.append(SyntheticPeak(w, a, f))
        return peaks

    def _rebuild(self, *_args) -> None:
        if self._loading:
            return
        if self._wl_max.value() <= self._wl_min.value():
            return  # invalid range; wait for a consistent edit
        spec = build_synthetic_spec(
            self._collect_peaks(),
            snr=self._snr.value(),
            baseline=self._baseline.value(),
            sample_interval=self._interval.value(),
            seed=self._seed.value(),
            wavelength_min=self._wl_min.value(),
            wavelength_max=self._wl_max.value(),
        )
        self._source.set_spec(spec)
        self._source.set_drift(self._drift.isChecked())
