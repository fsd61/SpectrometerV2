"""Main application window (Migration Plan Phase 7).

Milestone 5: a full menu bar + toolbar, the 13 original PySpectrometer2 keyboard
shortcuts (h s c x m p o l i k u j q), and snapshot/export wired through the
pluggable data sink. Earlier milestones added the live plot, scrolling
waterfall, control dock + readouts, and the synthetic-source panel.

The set of shortcuts, their menus, and their labels live in the Qt-free
``ui.live.LIVE_SHORTCUTS`` registry; this window just builds Qt actions from it
and binds each to a handler, so the shortcut table is unit-tested without a
display.
"""

from __future__ import annotations

import importlib.util
import logging
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from analysis.measurements import estimate_noise
from ui.analysis_params import SAFitParams, WaveletParams
from ui.live import (
    LIVE_SHORTCUTS,
    CalibrationSession,
    CameraFrameSource,
    LiveEngine,
    LiveParams,
    SyntheticFrameSource,
    build_frame_source,
    compare_centroid_methods,
    snap_pixel_to_peak,
    snapshot_spectrum,
)
from errors import CalibrationError
from .analysis_panel import AnalysisDock
from .controller import CaptureThread, TaskWorker
from .controls import ControlDock
from .spectrum_view import SpectrumView
from .synthetic_controls import SyntheticDock
from .waterfall_view import WaterfallView

_MENU_ORDER = ("File", "Calibrate", "Analysis")


class MainWindow(QtWidgets.QMainWindow):
    """The top-level SpectrometerV2 window."""

    def __init__(self, config=None, logger=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        self.setWindowTitle("SpectrometerV2")
        self.resize(1100, 700)

        frames = 256
        full_scale = None
        colormap = "inferno"
        waterfall_source = "raw"
        self._snapshot_dir = "snapshots"
        if config is not None:
            gui = config.section("gui")
            frames = int(gui.get("waterfall_frames", 256))
            # 0 means "no fixed ceiling" in the INI (the schema has no null), so
            # normalize it to None here rather than pushing the sentinel down.
            scale = float(gui.get("waterfall_full_scale", 0.0) or 0.0)
            full_scale = scale if scale > 0 else None
            colormap = str(gui.get("waterfall_colormap", "inferno"))
            waterfall_source = str(gui.get("waterfall_source", "raw"))
            self._snapshot_dir = str(gui.get("snapshot_dir", "snapshots"))

        self._params = LiveParams(measure=True)
        self._wavelet = (WaveletParams.from_config(config.section("wavelet"))
                         if config is not None else WaveletParams())
        self._sa = (SAFitParams.from_config(config.section("annealing"))
                    if config is not None else SAFitParams())
        self._last_result = None
        self._source = None
        self._fit_mode = False                # plot clicks fit lines when True
        self._worker: TaskWorker | None = None
        self._worker_kind = ""
        self._last_fit = None                 # (LineFitResult, wavelengths, source)
        self._last_comparison = None
        self._use_fitted = False
        self._extra_actions: dict[str, QtGui.QAction] = {}
        self._sink = None                     # built lazily on first snapshot
        self._last_spectrum = None
        self._last_peaks: list[int] = []      # peak pixel indices, for click-snap
        self._cal_session = CalibrationSession()
        self._calib_mode = False              # plot clicks add points when True
        self._engine: LiveEngine | None = None
        self._actions: dict[str, QtGui.QAction] = {}
        self._status_hold_until = 0.0         # live counter yields to a flashed msg

        self._view = SpectrumView()
        self._view.plotClicked.connect(self._on_plot_click)
        self._waterfall = WaterfallView(
            frames=frames, full_scale=full_scale, colormap=colormap,
            use_smoothed=(waterfall_source == "smoothed"),
        )
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self._view)
        splitter.addWidget(self._waterfall)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._dock = ControlDock(self._params, on_change=self._sync_controls)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
        self._synth_dock: SyntheticDock | None = None

        self._analysis = AnalysisDock(
            self._wavelet, self._sa,
            wavelet_available=importlib.util.find_spec("pywt") is not None,
        )
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._analysis)
        self.tabifyDockWidget(self._dock, self._analysis)
        self._dock.raise_()
        self._analysis.set_extraction_source(False)
        self._analysis.extractionChanged.connect(self._on_extraction_changed)
        self._analysis.denoiseToggled.connect(self._on_dock_denoise)
        self._analysis.fitModeToggled.connect(self._set_fit_mode)
        self._analysis.clearFitRequested.connect(self.act_clear_fit)
        self._analysis.cancelFitRequested.connect(self._cancel_worker)
        self._analysis.compareRequested.connect(self.act_compare_centroids)
        self._analysis.useFittedToggled.connect(self._set_use_fitted)
        self._analysis.rawOverlayToggled.connect(self._view.set_raw_overlay)

        self._build_menu()
        self._build_toolbar()
        self._sync_action_checks()

        self._thread: CaptureThread | None = None
        self._start_capture()

    # ------------------------------------------------------------------ #
    # Menu / toolbar construction (driven by ui.live.LIVE_SHORTCUTS)
    # ------------------------------------------------------------------ #
    def _make_action(self, spec) -> QtGui.QAction:
        act = QtGui.QAction(spec.label, self)
        act.setShortcut(QtGui.QKeySequence(spec.key))
        act.setToolTip(f"{spec.tip}  ({spec.key})")
        act.setStatusTip(spec.tip)
        if spec.checkable:
            act.setCheckable(True)
        handler = getattr(self, spec.handler)
        act.triggered.connect(lambda *_ignore, h=handler: h())
        self._actions[spec.key] = act
        return act

    def _build_menu(self) -> None:
        bar = self.menuBar()
        menus = {name: bar.addMenu(f"&{name}") for name in _MENU_ORDER}
        prev_menu = None
        for spec in LIVE_SHORTCUTS:
            act = self._make_action(spec)
            if prev_menu == spec.menu and spec.handler == "act_quit":
                menus[spec.menu].addSeparator()
            menus[spec.menu].addAction(act)
            prev_menu = spec.menu

        # Calibrate menu: a checkable "pick points" mode gates plot-click capture
        # (the c/x actions from the registry apply/clear the picked points).
        self._pick_action = QtGui.QAction("Pick points (click plot)", self)
        self._pick_action.setCheckable(True)
        self._pick_action.setShortcut("Ctrl+K")
        self._pick_action.setStatusTip(
            "Click emission lines on the plot to add calibration points, then press c."
        )
        self._pick_action.toggled.connect(self._toggle_pick_mode)
        menus["Calibrate"].addSeparator()
        menus["Calibrate"].addAction(self._pick_action)

        # SpectrometerV2 analysis additions (keys w, f are new; the 13 original
        # keys stay exactly as they were).
        use_fitted = self._extra_action("use_fitted", "Use fitted line centers",
                                        "Apply calibrations from sub-pixel fitted line centers",
                                        checkable=True)
        use_fitted.toggled.connect(self._set_use_fitted)
        compare = self._extra_action("compare", "Compare centroid methods…",
                                     "Leave-one-out calibration error: whole-pixel picks vs fitted centers")
        compare.triggered.connect(lambda *_: self.act_compare_centroids())
        menus["Calibrate"].addAction(use_fitted)
        menus["Calibrate"].addAction(compare)

        denoise = self._extra_action("w", "Wavelet denoising", "Denoise before smoothing "
                                     "and peak detection (FWHM/SNR stay on raw data)",
                                     checkable=True, key="w")
        denoise.setChecked(self._wavelet.denoise)
        denoise.toggled.connect(self._on_denoise_action)
        fit = self._extra_action("f", "Fit lines (click plot)", "Click a line to fit it by "
                                 "simulated annealing + least-squares polish",
                                 checkable=True, key="f")
        fit.toggled.connect(self._set_fit_mode)
        clear = self._extra_action("clear_fit", "Clear line fit", "Remove the fitted lines")
        clear.triggered.connect(lambda *_: self.act_clear_fit())
        menus["Analysis"].addSeparator()
        for act in (denoise, fit, clear):
            menus["Analysis"].addAction(act)

        self._view_menu = bar.addMenu("&View")
        toggle = self._dock.toggleViewAction()
        toggle.setText("Controls panel")
        toggle.setShortcut("Ctrl+B")
        self._view_menu.addAction(toggle)
        analysis_toggle = self._analysis.toggleViewAction()
        analysis_toggle.setText("Analysis panel")
        self._view_menu.addAction(analysis_toggle)

        help_menu = bar.addMenu("&Help")
        sc = QtGui.QAction("Keyboard shortcuts", self)
        sc.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F1))
        sc.triggered.connect(self._show_shortcuts)
        help_menu.addAction(sc)

    def _build_toolbar(self) -> None:
        tb = QtWidgets.QToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        self._toolbar = tb
        prev_menu = None
        for spec in LIVE_SHORTCUTS:
            if not spec.toolbar:
                continue
            if prev_menu is not None and spec.menu != prev_menu:
                tb.addSeparator()
            tb.addAction(self._actions[spec.key])
            prev_menu = spec.menu
        self._view_menu.addAction(tb.toggleViewAction())

    def _extra_action(self, name, label, tip, checkable=False, key=None) -> QtGui.QAction:
        act = QtGui.QAction(label, self)
        act.setStatusTip(tip)
        act.setToolTip(tip + (f"  ({key})" if key else ""))
        act.setCheckable(checkable)
        if key:
            act.setShortcut(QtGui.QKeySequence(key))
        self._extra_actions[name] = act
        return act

    def _show_shortcuts(self) -> None:
        rows = "\n".join(f"  {s.key}   {s.label}" for s in LIVE_SHORTCUTS)
        added = "\n".join(f"  {k}   {self._extra_actions[k].text()}" for k in ("w", "f"))
        QtWidgets.QMessageBox.information(
            self, "Keyboard shortcuts",
            "SpectrometerV2 live keys (from PySpectrometer2):\n\n" + rows
            + "\n\nAdded in SpectrometerV2:\n\n" + added,
        )

    # ------------------------------------------------------------------ #
    # Keeping menu / toolbar toggles in sync with the shared LiveParams
    # ------------------------------------------------------------------ #
    def _sync_action_checks(self) -> None:
        for key, attr in (("h", "hold_peaks"), ("m", "measure"), ("p", "pixel_mode")):
            act = self._actions.get(key)
            if act is not None:
                act.setChecked(bool(getattr(self._params, attr)))

    def _sync_controls(self) -> None:
        """Callback from the control dock: mirror its edits into the toggles."""
        self._sync_action_checks()

    def _after_param_change(self, message: str) -> None:
        self._sync_action_checks()
        self._dock.sync_from_params()
        self._flash_status(message, hold=1.5)

    # ------------------------------------------------------------------ #
    # Shortcut handlers (bound by key in LIVE_SHORTCUTS)
    # ------------------------------------------------------------------ #
    def act_snapshot(self) -> None:
        if self._last_spectrum is None:
            self._flash_status("Nothing to snapshot yet.")
            return
        try:
            path = snapshot_spectrum(
                self._last_spectrum, self._snapshot_dir, sink=self._snapshot_sink()
            )
        except Exception as exc:  # noqa: BLE001 - report, keep window alive
            self._flash_status(f"Snapshot failed: {exc}")
            self.logger.error("Snapshot failed: %s", exc)
            return
        self._flash_status(f"Saved snapshot → {path}")
        self.logger.info("Saved snapshot → %s", path)

    def _snapshot_sink(self):
        """The assembled sink for GUI snapshots (CSV + any enabled backends).

        Built once and reused, so an enabled SQLite store keeps a single
        connection rather than reopening on every snapshot keypress.
        """
        if self._sink is None and self.config is not None:
            from data.factory import build_sink

            self._sink = build_sink(self.config, self._snapshot_dir)
        return self._sink

    def act_quit(self) -> None:
        self.close()

    def act_calibrate(self) -> None:
        """Fit + apply a wavelength calibration from the picked points (key c)."""
        session = self._cal_session
        if not session.ready:
            self._flash_status(
                f"Calibration needs at least 3 points — {session.count} picked. "
                "Enable Calibrate ▸ Pick points and click emission lines."
            )
            return
        if self._use_fitted:
            if self._last_spectrum is None:
                self._flash_status("No frame yet to fit the picked lines on.")
                return
            intensities = list(self._last_spectrum.intensities)
            kwargs = self._sa.fit_kwargs()
            self._start_worker(
                "calibrate",
                lambda progress, stop: session.fitted_pixels(intensities, **kwargs),
                "Fitting line centers for the calibration…",
            )
            return
        self._apply_calibration(None)

    def _apply_calibration(self, pixels) -> None:
        """Fit + apply the calibration from the picks, or from ``pixels``
        (fitted sub-pixel centers) when given."""
        session = self._cal_session
        width = self._sensor_width()
        try:
            result = session.fit(width, pixels=pixels)
        except CalibrationError as exc:
            self._flash_status(f"Calibration failed: {exc}")
            self.logger.error("Calibration failed: %s", exc)
            return

        if self._engine is not None:
            # Pass the fit itself, not just the axis, so every calibrated frame
            # records which calibration produced it.
            self._engine.set_calibration(result.wavelengths, result)
        saved = self._save_calibration(session, pixels)
        r2 = "" if result.r_squared is None else f", R²={result.r_squared:.5f}"
        tail = f" → {saved}" if saved else ""
        how = "fitted centers" if pixels is not None else "picks"
        self._flash_status(
            f"Calibrated from {how}: {session.count} points, {result.order}-order fit{r2}{tail}"
        )
        self.logger.info("Applied calibration: %d points order=%d",
                         session.count, result.order)

    def act_clear_calibration(self) -> None:
        self._cal_session.clear()
        self._flash_status("Cleared picked calibration points.")

    # ------------------------------------------------------------------ #
    # Click-to-calibrate helpers (M6)
    # ------------------------------------------------------------------ #
    def _toggle_pick_mode(self, on: bool) -> None:
        if on and self._fit_mode:
            self._set_fit_mode(False)
        self._calib_mode = bool(on)
        self._flash_status(
            "Pick mode ON — click emission lines to add points, then press c."
            if on else "Pick mode off."
        )

    def _on_plot_click(self, x: float) -> None:
        if self._fit_mode:
            self._fit_at(self._x_to_pixel(x))
            return
        if not self._calib_mode:
            return
        pixel = snap_pixel_to_peak(x, self._last_peaks)
        wavelength, ok = QtWidgets.QInputDialog.getDouble(
            self, "Calibration point",
            f"Known wavelength (nm) at pixel {pixel}:",
            546.0, 0.0, 3000.0, 3,
        )
        if ok:
            self._add_calibration_pick(pixel, float(wavelength))

    def _add_calibration_pick(self, pixel: int, wavelength: float) -> None:
        """Record one (pixel, wavelength) pick. Split out so tests can drive it
        without the modal dialog."""
        self._cal_session.add(pixel, wavelength)
        self._flash_status(
            f"Point {self._cal_session.count}: pixel {pixel} = {wavelength:.2f} nm"
            + ("  (≥3 — press c to apply)" if self._cal_session.ready else "")
        )

    def _sensor_width(self) -> int:
        if self._last_spectrum is not None and len(self._last_spectrum) > 0:
            return len(self._last_spectrum)
        if self.config is not None:
            return int(self.config.section("camera").get("width", 1920))
        return 1920

    def _save_calibration(self, session, pixels=None) -> str:
        if self.config is None:
            return ""
        try:
            path = session.save(self.config.get("calibration", "file"), pixels=pixels)
            return str(path)
        except Exception as exc:  # noqa: BLE001 - non-fatal; calibration still applied
            self.logger.warning("Could not save calibration points: %s", exc)
            return ""

    def act_toggle_hold(self) -> None:
        state = self._params.toggle_hold_peaks()
        self._after_param_change(f"Hold peaks {'on' if state else 'off'}.")

    def act_toggle_measure(self) -> None:
        state = self._params.toggle_measure()
        self._after_param_change(f"Measure FWHM/SNR {'on' if state else 'off'}.")

    def act_toggle_pixel(self) -> None:
        state = self._params.toggle_pixel_mode()
        self._after_param_change(f"Pixel positions {'on' if state else 'off'}.")

    def act_savgol_up(self) -> None:
        self._params.adjust_savgol_order(1)
        self._after_param_change(f"Smoothing order = {self._params.savgol_order}")

    def act_savgol_down(self) -> None:
        self._params.adjust_savgol_order(-1)
        self._after_param_change(f"Smoothing order = {self._params.savgol_order}")

    def act_mindist_up(self) -> None:
        self._params.adjust_peak_min_dist(1)
        self._after_param_change(f"Peak min-distance = {self._params.peak_min_dist}")

    def act_mindist_down(self) -> None:
        self._params.adjust_peak_min_dist(-1)
        self._after_param_change(f"Peak min-distance = {self._params.peak_min_dist}")

    def act_thresh_up(self) -> None:
        self._params.adjust_threshold(1)
        self._after_param_change(f"Threshold = {self._params.peak_thres:.2f}")

    def act_thresh_down(self) -> None:
        self._params.adjust_threshold(-1)
        self._after_param_change(f"Threshold = {self._params.peak_thres:.2f}")

    # ------------------------------------------------------------------ #
    # Live capture (milestones 2-4.5)
    # ------------------------------------------------------------------ #
    def _start_capture(self) -> None:
        if self.config is None:
            self.statusBar().showMessage("No configuration — idle")
            return
        try:
            source = build_frame_source(self.config, self.logger)
        except Exception as exc:  # noqa: BLE001 - report, keep window alive
            self.statusBar().showMessage(f"Could not start capture: {exc}")
            self.logger.error("Could not start capture: %s", exc)
            return

        # Synthetic mode only: a live signal-generator dock, clearly labeled.
        if isinstance(source, SyntheticFrameSource):
            self.setWindowTitle("SpectrometerV2 — [SIMULATED]")
            self._synth_dock = SyntheticDock(source)
            self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._synth_dock)
            self.tabifyDockWidget(self._dock, self._synth_dock)
            self._dock.raise_()
            toggle = self._synth_dock.toggleViewAction()
            toggle.setText("Synthetic source panel")
            self._view_menu.addAction(toggle)

        self._source = source
        if isinstance(source, CameraFrameSource):
            self._analysis.set_extraction_source(True, source.average_rows, source.precision)
            from cameras.synthetic_camera import SyntheticCameraAdapter

            if isinstance(source.camera, SyntheticCameraAdapter):
                self.setWindowTitle("SpectrometerV2 — [SIMULATED CAMERA]")

        engine = LiveEngine(source, self._params, wavelet=self._wavelet)
        self._engine = engine
        fps = float(self.config.section("gui").get("fps", 15.0))
        self._thread = CaptureThread(engine, fps=fps)
        self._thread.frameReady.connect(self._on_frame)
        self._thread.error.connect(self._on_error)
        self._thread.start()
        self.statusBar().showMessage("Live")

    def _flash_status(self, message: str, hold: float = 3.0) -> None:
        """Show a message and hold it against the per-frame live counter.

        The capture thread rewrites the status bar every frame; without this a
        user-action confirmation (snapshot saved, calibration applied) would be
        overwritten within ~1/fps of a second and never be readable.
        """
        self.statusBar().showMessage(message)
        self._status_hold_until = time.monotonic() + hold

    def _on_frame(self, spectrum, result) -> None:
        self._last_spectrum = spectrum
        self._last_result = result
        self._last_peaks = [p.pixel for p in result.peaks]
        self._view.update_spectrum(spectrum, result)
        self._waterfall.update_spectrum(spectrum, result)
        self._dock.update_readouts(spectrum, result)
        self._update_analysis_readouts(spectrum, result)
        if time.monotonic() >= self._status_hold_until:
            self.statusBar().showMessage(
                f"Live — {len(spectrum)} samples, {len(result.peaks)} peaks"
            )

    # ------------------------------------------------------------------ #
    # Analysis panel: extraction band, denoising, line fitting, A/B check
    # ------------------------------------------------------------------ #
    def _update_analysis_readouts(self, spectrum, result) -> None:
        if isinstance(self._source, CameraFrameSource):
            limit = self._source.max_band_height()
            if limit:
                self._analysis.set_extraction_limit(limit)
        engine_error = self._engine.denoise_error if self._engine is not None else None
        if engine_error:
            self._analysis.show_denoise_error(engine_error)
            return
        if len(spectrum.intensities) < 20:
            return
        raw = np.asarray(spectrum.intensities, dtype=float)
        den = getattr(result, "denoised", None)
        removed = (float(np.sqrt(np.mean((raw - np.asarray(den, dtype=float)) ** 2)))
                   if den is not None else None)
        self._analysis.update_noise(estimate_noise(raw), removed)

    def _on_extraction_changed(self, rows: int, precision: str) -> None:
        source = self._source
        if not isinstance(source, CameraFrameSource):
            return
        try:
            source.set_extraction(rows, precision)
        except ValueError as exc:
            self._flash_status(str(exc))
            self._analysis.revert_extraction(source.average_rows, source.precision)
            return
        self._flash_status(f"Slice height {rows} rows, {precision} precision.")

    def _on_denoise_action(self, checked: bool) -> None:
        self._wavelet.denoise = bool(checked)
        self._analysis.sync_denoise()
        self._flash_status(f"Wavelet denoising {'on' if checked else 'off'}.")

    def _on_dock_denoise(self, checked: bool) -> None:
        act = self._extra_actions.get("w")
        if act is not None:
            act.blockSignals(True)
            act.setChecked(bool(checked))
            act.blockSignals(False)
        self._flash_status(f"Wavelet denoising {'on' if checked else 'off'}.")

    def _set_fit_mode(self, on: bool) -> None:
        on = bool(on)
        if on and self._calib_mode:
            self._pick_action.setChecked(False)
        self._fit_mode = on
        act = self._extra_actions.get("f")
        if act is not None and act.isChecked() != on:
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)
        self._analysis.set_fit_mode(on)
        self._flash_status("Fit mode ON — click a line on the plot." if on else "Fit mode off.")

    def _set_use_fitted(self, on: bool) -> None:
        self._use_fitted = bool(on)
        act = self._extra_actions.get("use_fitted")
        if act is not None and act.isChecked() != self._use_fitted:
            act.blockSignals(True)
            act.setChecked(self._use_fitted)
            act.blockSignals(False)
        self._analysis.set_use_fitted(self._use_fitted)
        self._flash_status("Calibrations will use fitted line centers." if on
                           else "Calibrations will use the whole-pixel picks.")

    def _x_to_pixel(self, x: float) -> float:
        """Plot x (nm on a calibrated axis, else pixel) -> pixel index."""
        spec = self._last_spectrum
        if spec is not None and len(spec.wavelengths) > 0:
            wl = np.asarray(spec.wavelengths, dtype=float)
            return float(np.argmin(np.abs(wl - float(x))))
        return float(x)

    def _fit_at(self, center_px: float, window: int = 12) -> None:
        """Fit the line(s) around ``center_px`` on the latest frame, in the background."""
        spectrum, result = self._last_spectrum, self._last_result
        if spectrum is None or result is None:
            self._flash_status("No frame to fit yet.")
            return
        seeds = [p.pixel for p in result.peaks if abs(p.pixel - center_px) <= window]
        if not seeds:
            seeds = [int(round(center_px))]
        n_lines = self._analysis.n_lines or len(seeds)
        use_denoised = self._sa.fit_denoised and getattr(result, "denoised", None) is not None
        data = list(result.denoised) if use_denoised else list(spectrum.intensities)
        wavelengths = list(spectrum.wavelengths) if len(spectrum.wavelengths) else None
        kwargs = self._sa.fit_kwargs()
        from analysis.linefit import fit_lines

        self._fit_context = (wavelengths, "denoised" if use_denoised else "raw")
        self._start_worker(
            "fit",
            lambda progress, stop: fit_lines(data, seeds, n_lines=n_lines, wavelengths=wavelengths,
                                             progress=progress, should_stop=stop, **kwargs),
            f"Fitting {n_lines} line{'s' if n_lines != 1 else ''} near pixel {int(round(center_px))}…",
        )

    def _start_worker(self, kind: str, fn, message: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._flash_status("A fit is already running — wait or cancel it.")
            return
        worker = TaskWorker(fn, self)
        self._worker, self._worker_kind = worker, kind
        worker.progress.connect(self._analysis.fit_progress)
        worker.finished_ok.connect(self._on_worker_done)
        worker.failed.connect(self._on_worker_failed)
        self._analysis.fit_started()
        self._flash_status(message, hold=60.0)
        worker.start()

    def _cancel_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def _on_worker_done(self, value) -> None:
        kind, worker = self._worker_kind, self._worker
        cancelled = worker is not None and worker.cancelled
        if kind == "fit":
            if cancelled:
                self._analysis.fit_finished(None, message="Fit cancelled.")
                self._flash_status("Fit cancelled.")
                return
            wavelengths, source = self._fit_context
            self._last_fit = (value, wavelengths, source)
            self._view.show_fit(value, wavelengths)
            self._analysis.fit_finished(value, source)
            centers = ", ".join(
                f"{ln.center_nm:.3f} nm" if ln.center_nm is not None else f"{ln.center_px:.2f} px"
                for ln in value.lines)
            self._flash_status(f"Fitted {len(value.lines)} line(s): {centers}", hold=6.0)
            self.logger.info("Line fit (%s spectrum, seed %s): %s", source, value.seed, centers)
        elif kind == "calibrate":
            self._analysis.fit_finished(None, message="Line centers fitted for calibration.")
            self._apply_calibration(value)
        elif kind == "compare":
            self._analysis.fit_finished(None, message="Centroid comparison done.")
            self._last_comparison = value
            self._show_comparison(value)

    def _on_worker_failed(self, message: str) -> None:
        self._analysis.fit_finished(None, message=f"Failed: {message}")
        self._flash_status(f"Failed: {message}")
        self.logger.error("Analysis task failed: %s", message)

    def act_clear_fit(self) -> None:
        self._last_fit = None
        self._view.clear_fit()
        self._analysis.clear_fit()

    def act_compare_centroids(self) -> None:
        session = self._cal_session
        if session.count < 4:
            self._flash_status(f"The comparison needs at least 4 picked lines — {session.count} picked.")
            return
        if self._last_spectrum is None:
            self._flash_status("No frame yet to fit the picked lines on.")
            return
        intensities = list(self._last_spectrum.intensities)
        kwargs = self._sa.fit_kwargs()
        self._start_worker(
            "compare",
            lambda progress, stop: compare_centroid_methods(session, intensities, **kwargs),
            "Comparing whole-pixel picks with fitted line centers…",
        )

    def _show_comparison(self, comp) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Calibration: picks vs fitted line centers")
        v = QtWidgets.QVBoxLayout(dlg)
        headers = ["Known (nm)", "Pick (px)", "Fitted (px)", "Error, pick (nm)", "Error, fitted (nm)"]
        table = QtWidgets.QTableWidget(len(comp.rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, row in enumerate(comp.rows):
            values = [f"{row.wavelength:.3f}", f"{row.pick_px:.0f}", f"{row.fitted_px:.2f}",
                      f"{row.residual_pick:+.3f}", f"{row.residual_fitted:+.3f}"]
            for c, text in enumerate(values):
                table.setItem(r, c, QtWidgets.QTableWidgetItem(text))
        table.resizeColumnsToContents()
        v.addWidget(table)
        better = comp.improvement
        verdict = ("" if better is None else
                   f" — fitted centers are {abs(better) * 100:.0f}% "
                   f"{'better' if better >= 0 else 'worse'}")
        summary = QtWidgets.QLabel(
            f"Leave-one-out RMS error: picks {comp.rms_pick:.3f} nm, "
            f"fitted {comp.rms_fitted:.3f} nm{verdict}.\n"
            "Each line's wavelength is predicted from a calibration fitted to the "
            "other lines, so the errors measure real predictive accuracy."
        )
        summary.setWordWrap(True)
        v.addWidget(summary)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        dlg.resize(620, 360)
        self.logger.info("Centroid comparison: RMS picks %.4f nm, fitted %.4f nm",
                         comp.rms_pick, comp.rms_fitted)
        dlg.open()
        self._comparison_dialog = dlg

    def _on_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Capture stopped: {message}")
        self.logger.error("Capture error: %s", message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        if self._thread is not None:
            self._thread.stop()
            self._thread = None
        super().closeEvent(event)
