"""Analysis dock: extraction band, wavelet denoising, line fitting, calibration check.

The controls here edit shared, Qt-free parameter objects (``WaveletParams``,
``SAFitParams``) that the capture thread or the fit worker read, exactly as the
Controls dock edits ``LiveParams``. Anything that must be validated against the
live source (the extraction band) or run off the UI thread (line fitting, the
centroid comparison) is requested through signals and handled by the main
window.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from reference import available_species
from ui.analysis_params import SAFitParams, WaveletParams

_HEIGHT_TIP = (
    "Rows of the slit image averaged into each spectral sample (odd).\n"
    "3 matches PySpectrometer2. Random noise falls as 1/sqrt(rows), so a taller "
    "band gives more signal-to-noise, as long as every row is inside the bright "
    "slit image. It does not improve resolution."
)
_FLOAT_TIP = (
    "Keep the fractional part of each averaged sample.\n"
    "With a tall band the noise falls below one count; rounding to whole counts "
    "(as PySpectrometer2 does) would throw most of the gain away."
)
_DENOISE_TIP = (
    "Wavelet denoising ahead of smoothing and peak detection (key w).\n"
    "It reads the raw spectrum and never replaces it. FWHM and SNR are always "
    "measured on the raw data, because a denoised trace has artificially low noise."
)
_MODE_TIP = (
    "hard: keep surviving coefficients unchanged (preserves line height).\n"
    "soft: shrink them (smoother, but lowers and can shift dim lines)."
)
_SCALE_TIP = (
    "Multiplier on the universal threshold sigma*sqrt(2 ln N).\n"
    "1.0 is the textbook value but flattens dim lines; 0.6 removes less noise "
    "and keeps them intact."
)
_LINES_TIP = (
    "How many lines to fit around the click. 0 = one per detected peak nearby.\n"
    "Set 2 to split a doublet that peak detection sees as one line."
)
_FIT_TIP = (
    "Click a line on the plot to fit it (key f).\n"
    "Simulated annealing (DiGennaro & Cowburn, 1992) finds the lines; a "
    "Levenberg-Marquardt polish then pins their centers to sub-pixel precision."
)
_FIT_DENOISED_TIP = (
    "Fit the denoised spectrum instead of the raw one.\n"
    "Off by default: denoising cannot add information, and measured on simulated "
    "lines it never made fitted centers more precise. On, it lets you compare."
)
_USE_FITTED_TIP = (
    "When applying a calibration (key c), use sub-pixel line centers fitted at "
    "each picked line instead of the whole-pixel picks."
)
_COMPARE_TIP = (
    "Leave-one-out test of the picked calibration lines: predict each line's "
    "wavelength from the others, once with whole-pixel picks and once with "
    "fitted centers. Needs 4 or more picked lines."
)

_IDENTIFY_TIP = (
    "Click a peak on a calibrated plot to list the NIST reference lines near it "
    "(key n).\nThe peak's wavelength comes from the current calibration, so a "
    "poor calibration gives poor matches."
)
_TOLERANCE_TIP = (
    "How far from the peak to look for reference lines.\n"
    "About 4 pixels (1 nm at 0.27 nm/px) suits a good calibration; widen it if "
    "the calibration is rough."
)
# The FS-2 lamp (argon), fluorescent tubes (mercury), neon indicator lamps and
# the sodium D lines: the sources this instrument is likely to see.
_DEFAULT_SPECIES = ("Ar I", "Hg I", "Ne I", "Na I")

_FIT_COLUMNS = ["Line", "Center", "FWHM", "Amplitude"]
_ID_COLUMNS = ["Element", "Wavelength", "Δ", "Strength"]


def _tip(widget, text):
    widget.setToolTip(text)
    widget.setStatusTip(text.split("\n")[0])
    return widget


class AnalysisDock(QtWidgets.QDockWidget):
    """Right-hand dock with the analysis controls added in SpectrometerV2."""

    extractionChanged = QtCore.Signal(int, str)    # rows, precision
    denoiseToggled = QtCore.Signal(bool)
    fitModeToggled = QtCore.Signal(bool)
    clearFitRequested = QtCore.Signal()
    cancelFitRequested = QtCore.Signal()
    compareRequested = QtCore.Signal()
    useFittedToggled = QtCore.Signal(bool)
    rawOverlayToggled = QtCore.Signal(bool)
    identifyModeToggled = QtCore.Signal(bool)
    identifySettingsChanged = QtCore.Signal()

    def __init__(self, wavelet: WaveletParams, sa: SAFitParams, parent=None,
                 wavelet_available: bool = True):
        super().__init__("Analysis", parent)
        self.setObjectName("AnalysisDock")
        self._wavelet = wavelet
        self._sa = sa

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.addWidget(self._build_extraction())
        layout.addWidget(self._build_wavelet(wavelet_available))
        layout.addWidget(self._build_fit())
        layout.addWidget(self._build_calibration())
        layout.addWidget(self._build_identify())
        layout.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setWidget(scroll)

    # ------------------------------------------------------------------ #
    # Extraction band
    # ------------------------------------------------------------------ #
    def _build_extraction(self):
        box = QtWidgets.QGroupBox("Extraction")
        form = QtWidgets.QFormLayout(box)
        self._height = _tip(QtWidgets.QSpinBox(), _HEIGHT_TIP)
        self._height.setRange(1, 4095)
        self._height.setSingleStep(2)
        self._height.setValue(3)
        self._height.setKeyboardTracking(False)
        self._height.valueChanged.connect(self._on_height)
        form.addRow("Slice height (rows)", self._height)
        self._float = _tip(QtWidgets.QCheckBox("Keep fraction (float precision)"), _FLOAT_TIP)
        self._float.toggled.connect(self._emit_extraction)
        form.addRow(self._float)
        self._extract_note = QtWidgets.QLabel("")
        self._extract_note.setWordWrap(True)
        form.addRow(self._extract_note)
        return box

    def set_extraction_source(self, available: bool, rows: int = 3,
                              precision: str = "integer", max_rows=None) -> None:
        """Enable the extraction controls for a camera source, or explain why not."""
        for w in (self._height, self._float):
            w.blockSignals(True)
        self._height.setValue(int(rows))
        self._float.setChecked(precision == "float")
        if max_rows:
            self._height.setMaximum(int(max_rows))
        for w in (self._height, self._float):
            w.blockSignals(False)
        self._height.setEnabled(available)
        self._float.setEnabled(available)
        self._extract_note.setText(
            "" if available else
            "Simulated spectra are generated directly, with no camera frame to "
            "slice. Use a camera, or camera.backend = synthetic-camera."
        )

    def set_extraction_limit(self, max_rows: int) -> None:
        self._height.setMaximum(int(max_rows))

    def _on_height(self, value: int) -> None:
        if value % 2 == 0:              # keep it odd: step towards where the user was going
            self._height.setValue(value + 1 if value < self._height.maximum() else value - 1)
            return
        self._emit_extraction()

    def _emit_extraction(self, *_):
        self.extractionChanged.emit(int(self._height.value()),
                                    "float" if self._float.isChecked() else "integer")

    def revert_extraction(self, rows: int, precision: str) -> None:
        """Restore the controls after the source rejected a value."""
        self.set_extraction_source(True, rows, precision)

    # ------------------------------------------------------------------ #
    # Wavelet denoising
    # ------------------------------------------------------------------ #
    def _build_wavelet(self, available: bool):
        box = QtWidgets.QGroupBox("Wavelet denoising")
        form = QtWidgets.QFormLayout(box)
        w = self._wavelet
        self._denoise = _tip(QtWidgets.QCheckBox("Denoise (w)"), _DENOISE_TIP)
        self._denoise.setChecked(w.denoise)
        self._denoise.toggled.connect(self._on_denoise)
        form.addRow(self._denoise)

        self._family = QtWidgets.QComboBox()
        self._family.addItems(list(WaveletParams.WAVELET_CHOICES))
        self._family.setCurrentText(w.wavelet)
        self._family.currentTextChanged.connect(lambda t: w.set_wavelet(t))
        form.addRow("Family", _tip(self._family, "sym5 and coif3 are nearly symmetric, "
                                   "so they do not pull line centers."))

        self._level = QtWidgets.QSpinBox()
        self._level.setRange(WaveletParams.LEVEL_MIN, WaveletParams.LEVEL_MAX)
        self._level.setValue(w.level)
        self._level.valueChanged.connect(lambda v: w.set_level(v))
        form.addRow("Level", _tip(self._level, "Decomposition depth; clamped to what "
                                  "the spectrum length allows."))

        self._mode = _tip(QtWidgets.QComboBox(), _MODE_TIP)
        self._mode.addItems(list(WaveletParams.MODE_CHOICES))
        self._mode.setCurrentText(w.threshold_mode)
        self._mode.currentTextChanged.connect(lambda t: w.set_threshold_mode(t))
        form.addRow("Threshold", self._mode)

        self._scale = _tip(QtWidgets.QDoubleSpinBox(), _SCALE_TIP)
        self._scale.setRange(WaveletParams.SCALE_MIN, WaveletParams.SCALE_MAX)
        self._scale.setSingleStep(0.1)
        self._scale.setDecimals(2)
        self._scale.setValue(w.threshold_scale)
        self._scale.valueChanged.connect(lambda v: w.set_threshold_scale(v))
        form.addRow("Threshold scale", self._scale)

        self._raw_overlay = QtWidgets.QCheckBox("Show raw spectrum behind")
        self._raw_overlay.setChecked(True)
        self._raw_overlay.toggled.connect(self.rawOverlayToggled.emit)
        form.addRow(self._raw_overlay)

        self._noise_lbl = _tip(QtWidgets.QLabel("Noise: —"), (
            "Raw noise, and how much the denoiser removed (RMS of raw minus denoised).\n"
            "About 1x the noise means it is removing noise; well above 1x means it is "
            "also removing signal, so lower the threshold scale."))
        self._noise_lbl.setWordWrap(True)
        form.addRow(self._noise_lbl)

        if not available:
            for widget in (self._denoise, self._family, self._level, self._mode, self._scale):
                widget.setEnabled(False)
            self._noise_lbl.setText("PyWavelets is not installed: pip install -e .[wavelet]")
        return box

    @property
    def raw_overlay(self) -> bool:
        return self._raw_overlay.isChecked()

    def _on_denoise(self, checked: bool) -> None:
        self._wavelet.denoise = bool(checked)
        self.denoiseToggled.emit(bool(checked))

    def sync_denoise(self) -> None:
        self._denoise.blockSignals(True)
        self._denoise.setChecked(self._wavelet.denoise)
        self._denoise.blockSignals(False)

    def update_noise(self, raw_sigma, removed_rms=None) -> None:
        """Show the raw noise and, when denoising, how much was removed.

        Deliberately not "denoised noise": the roughness of a denoised trace
        mostly measures the smoothing, not the remaining error, and would
        overstate the gain several-fold.
        """
        if raw_sigma is None:
            self._noise_lbl.setText("Noise: —")
        elif removed_rms is None:
            self._noise_lbl.setText(f"Raw noise σ {raw_sigma:.2f} counts")
        else:
            ratio = removed_rms / raw_sigma if raw_sigma > 0 else float("inf")
            self._noise_lbl.setText(
                f"Raw noise σ {raw_sigma:.2f} · removed {removed_rms:.2f} RMS ({ratio:.2f}x noise)")

    def show_denoise_error(self, message: str) -> None:
        self._noise_lbl.setText(f"Denoising unavailable: {message}")

    # ------------------------------------------------------------------ #
    # Line fitting (simulated annealing)
    # ------------------------------------------------------------------ #
    def _build_fit(self):
        box = QtWidgets.QGroupBox("Line fitting (simulated annealing)")
        v = QtWidgets.QVBoxLayout(box)
        form = QtWidgets.QFormLayout()
        sa = self._sa

        self._n_lines = _tip(QtWidgets.QSpinBox(), _LINES_TIP)
        self._n_lines.setRange(0, 8)
        self._n_lines.setSpecialValueText("auto")
        self._n_lines.setValue(min(8, sa.n_components))
        self._n_lines.valueChanged.connect(lambda val: sa.set_n_components(val))
        form.addRow("Lines to fit", self._n_lines)

        self._schedule = QtWidgets.QComboBox()
        self._schedule.addItems(list(SAFitParams.SCHEDULE_CHOICES))
        self._schedule.setCurrentText(sa.schedule)
        self._schedule.currentTextChanged.connect(lambda t: sa.set_schedule(t))
        form.addRow("Cooling", _tip(self._schedule, "Annealing temperature schedule: "
                                    "fast (log), medium (geometric), slow (linear)."))

        self._cycles = QtWidgets.QSpinBox()
        self._cycles.setRange(SAFitParams.MAX_CYCLES_MIN, SAFitParams.MAX_CYCLES_MAX)
        self._cycles.setValue(sa.max_cycles)
        self._cycles.valueChanged.connect(lambda val: setattr(sa, "max_cycles", int(val)))
        form.addRow("Max cycles", _tip(self._cycles, "Compute budget. Fits usually stop "
                                       "well before this, once the cost stops improving."))

        seed_row = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(seed_row)
        h.setContentsMargins(0, 0, 0, 0)
        self._seed = QtWidgets.QSpinBox()
        self._seed.setRange(0, 2**31 - 1)
        self._seed.setValue(sa.seed)
        self._seed.valueChanged.connect(lambda val: setattr(sa, "seed", int(val)))
        self._lock = QtWidgets.QCheckBox("locked")
        self._lock.setChecked(sa.lock_seed)
        self._lock.toggled.connect(lambda c: setattr(sa, "lock_seed", bool(c)))
        h.addWidget(self._seed, 1)
        h.addWidget(self._lock)
        form.addRow("Seed", _tip(seed_row, "Random seed, recorded with every fit. Locked "
                                 "= reproducible; unlocked = a fresh run each time."))

        self._fit_denoised = _tip(QtWidgets.QCheckBox("Fit the denoised spectrum"), _FIT_DENOISED_TIP)
        self._fit_denoised.setChecked(sa.fit_denoised)
        self._fit_denoised.toggled.connect(lambda c: setattr(sa, "fit_denoised", bool(c)))
        form.addRow(self._fit_denoised)
        v.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        self._fit_btn = _tip(QtWidgets.QPushButton("Fit lines (click plot)"), _FIT_TIP)
        self._fit_btn.setCheckable(True)
        self._fit_btn.toggled.connect(self.fitModeToggled.emit)
        clear = QtWidgets.QPushButton("Clear fit")
        clear.clicked.connect(self.clearFitRequested.emit)
        buttons.addWidget(self._fit_btn, 1)
        buttons.addWidget(clear)
        v.addLayout(buttons)

        prog_row = QtWidgets.QHBoxLayout()
        self._progress = QtWidgets.QProgressBar()
        self._progress.setVisible(False)
        self._cancel = QtWidgets.QPushButton("Cancel")
        self._cancel.setVisible(False)
        self._cancel.clicked.connect(self.cancelFitRequested.emit)
        prog_row.addWidget(self._progress, 1)
        prog_row.addWidget(self._cancel)
        v.addLayout(prog_row)

        self._fit_table = QtWidgets.QTableWidget(0, len(_FIT_COLUMNS))
        self._fit_table.setHorizontalHeaderLabels(_FIT_COLUMNS)
        self._fit_table.horizontalHeader().setStretchLastSection(True)
        self._fit_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fit_table.verticalHeader().setVisible(False)
        self._fit_table.setMinimumHeight(90)
        self._fit_table.setMaximumHeight(150)
        v.addWidget(self._fit_table)
        self._fit_summary = QtWidgets.QLabel("No fit yet.")
        self._fit_summary.setWordWrap(True)
        v.addWidget(self._fit_summary)
        return box

    @property
    def n_lines(self) -> int:
        return int(self._n_lines.value())

    def set_fit_mode(self, on: bool) -> None:
        self._fit_btn.blockSignals(True)
        self._fit_btn.setChecked(bool(on))
        self._fit_btn.blockSignals(False)

    def fit_started(self) -> None:
        self._progress.setRange(0, max(1, self._sa.max_cycles))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._cancel.setVisible(True)
        self._fit_summary.setText("Fitting…")

    def fit_progress(self, cycle: int, total: int) -> None:
        self._progress.setRange(0, max(1, int(total)))
        self._progress.setValue(int(cycle))

    def fit_finished(self, result=None, source: str = "raw", message: str = "") -> None:
        self._progress.setVisible(False)
        self._cancel.setVisible(False)
        if result is None:
            self._fit_summary.setText(message or "No fit.")
            return
        self._fit_table.setRowCount(len(result.lines))
        for r, line in enumerate(result.lines):
            center = (f"{line.center_nm:.3f} nm" if line.center_nm is not None
                      else f"{line.center_px:.2f} px")
            fwhm = (f"{line.fwhm_nm:.3f} nm" if line.fwhm_nm is not None
                    else f"{line.fwhm_px:.2f} px")
            if line.center_nm is not None:
                center += f"  ({line.center_px:.2f} px)"
            values = [str(r + 1), center, fwhm, f"{line.amplitude:.1f}"]
            for c, text in enumerate(values):
                self._fit_table.setItem(r, c, QtWidgets.QTableWidgetItem(text))
        self._fit_table.resizeColumnsToContents()
        seed = "fresh" if result.seed is None else str(result.seed)
        self._fit_summary.setText(
            f"RMS residual {result.rms_residual:.2f} counts · {result.cycles} cycles · "
            f"seed {seed} · best: {getattr(result, 'method', 'annealing')} · "
            f"fitted on the {source} spectrum"
        )

    def clear_fit(self) -> None:
        self._fit_table.setRowCount(0)
        self._fit_summary.setText("No fit yet.")

    # ------------------------------------------------------------------ #
    # Calibration check
    # ------------------------------------------------------------------ #
    def _build_calibration(self):
        box = QtWidgets.QGroupBox("Calibration check")
        v = QtWidgets.QVBoxLayout(box)
        self._use_fitted = _tip(QtWidgets.QCheckBox("Use fitted line centers"), _USE_FITTED_TIP)
        self._use_fitted.toggled.connect(self.useFittedToggled.emit)
        v.addWidget(self._use_fitted)
        btn = _tip(QtWidgets.QPushButton("Compare centroid methods…"), _COMPARE_TIP)
        btn.clicked.connect(self.compareRequested.emit)
        v.addWidget(btn)
        return box

    def set_use_fitted(self, on: bool) -> None:
        self._use_fitted.blockSignals(True)
        self._use_fitted.setChecked(bool(on))
        self._use_fitted.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Line identification (NIST reference lines)
    # ------------------------------------------------------------------ #
    def _build_identify(self):
        box = QtWidgets.QGroupBox("Line identification (NIST)")
        v = QtWidgets.QVBoxLayout(box)

        self._identify_btn = _tip(QtWidgets.QPushButton("Identify lines (click plot)"),
                                  _IDENTIFY_TIP)
        self._identify_btn.setCheckable(True)
        self._identify_btn.toggled.connect(self.identifyModeToggled.emit)
        v.addWidget(self._identify_btn)

        grid = QtWidgets.QGridLayout()
        self._species_boxes: dict[str, QtWidgets.QCheckBox] = {}
        for i, name in enumerate(available_species()):
            cb = QtWidgets.QCheckBox(name)
            cb.setChecked(name in _DEFAULT_SPECIES)
            cb.toggled.connect(lambda *_: self.identifySettingsChanged.emit())
            self._species_boxes[name] = cb
            grid.addWidget(cb, i // 4, i % 4)
        v.addLayout(grid)

        form = QtWidgets.QFormLayout()
        self._tolerance = _tip(QtWidgets.QDoubleSpinBox(), _TOLERANCE_TIP)
        self._tolerance.setRange(0.05, 10.0)
        self._tolerance.setSingleStep(0.25)
        self._tolerance.setDecimals(2)
        self._tolerance.setSuffix(" nm")
        self._tolerance.setValue(1.0)
        self._tolerance.valueChanged.connect(lambda *_: self.identifySettingsChanged.emit())
        form.addRow("Search ±", self._tolerance)
        v.addLayout(form)

        self._id_table = QtWidgets.QTableWidget(0, len(_ID_COLUMNS))
        self._id_table.setHorizontalHeaderLabels(_ID_COLUMNS)
        self._id_table.horizontalHeader().setStretchLastSection(True)
        self._id_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._id_table.verticalHeader().setVisible(False)
        self._id_table.setMinimumHeight(90)
        self._id_table.setMaximumHeight(170)
        v.addWidget(self._id_table)
        self._id_summary = QtWidgets.QLabel("Click a peak in Identify mode.")
        self._id_summary.setWordWrap(True)
        v.addWidget(self._id_summary)
        return box

    def selected_species(self) -> list[str]:
        return [name for name, cb in self._species_boxes.items() if cb.isChecked()]

    @property
    def tolerance_nm(self) -> float:
        return float(self._tolerance.value())

    def set_identify_mode(self, on: bool) -> None:
        self._identify_btn.blockSignals(True)
        self._identify_btn.setChecked(bool(on))
        self._identify_btn.blockSignals(False)

    def show_identification(self, measured_nm: float, position_px: float, candidates) -> None:
        self._id_table.setRowCount(len(candidates))
        for r, c in enumerate(candidates):
            values = [c.species, f"{c.wavelength_nm:.3f} nm", f"{c.delta_nm:+.2f} nm",
                      c.strength or "—"]
            for col, text in enumerate(values):
                self._id_table.setItem(r, col, QtWidgets.QTableWidgetItem(text))
        self._id_table.resizeColumnsToContents()
        head = f"Peak at {measured_nm:.2f} nm (pixel {position_px:.1f})."
        if not self.selected_species():
            self._id_summary.setText(head + " Tick at least one element.")
        elif not candidates:
            self._id_summary.setText(
                head + f" No {', '.join(self.selected_species())} line within "
                f"±{self.tolerance_nm:g} nm.")
        else:
            self._id_summary.setText(head + " Nearest first; Δ = reference minus measured.")

    def clear_identification(self, message: str = "Click a peak in Identify mode.") -> None:
        self._id_table.setRowCount(0)
        self._id_summary.setText(message)
