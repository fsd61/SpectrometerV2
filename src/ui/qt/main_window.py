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

import logging
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ui.live import (
    LIVE_SHORTCUTS,
    CalibrationSession,
    LiveEngine,
    LiveParams,
    SyntheticFrameSource,
    build_frame_source,
    snap_pixel_to_peak,
    snapshot_spectrum,
)
from errors import CalibrationError
from .controller import CaptureThread
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
        self._snapshot_dir = "snapshots"
        if config is not None:
            gui = config.section("gui")
            frames = int(gui.get("waterfall_frames", 256))
            self._snapshot_dir = str(gui.get("snapshot_dir", "snapshots"))

        self._params = LiveParams(measure=True)
        self._last_spectrum = None
        self._last_peaks: list[int] = []      # peak pixel indices, for click-snap
        self._cal_session = CalibrationSession()
        self._calib_mode = False              # plot clicks add points when True
        self._engine: LiveEngine | None = None
        self._actions: dict[str, QtGui.QAction] = {}
        self._status_hold_until = 0.0         # live counter yields to a flashed msg

        self._view = SpectrumView()
        self._view.plotClicked.connect(self._on_plot_click)
        self._waterfall = WaterfallView(frames=frames)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self._view)
        splitter.addWidget(self._waterfall)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._dock = ControlDock(self._params, on_change=self._sync_controls)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
        self._synth_dock: SyntheticDock | None = None

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

        self._view_menu = bar.addMenu("&View")
        toggle = self._dock.toggleViewAction()
        toggle.setText("Controls panel")
        toggle.setShortcut("Ctrl+B")
        self._view_menu.addAction(toggle)

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

    def _show_shortcuts(self) -> None:
        rows = "\n".join(f"  {s.key}   {s.label}" for s in LIVE_SHORTCUTS)
        QtWidgets.QMessageBox.information(
            self, "Keyboard shortcuts",
            "SpectrometerV2 live keys (from PySpectrometer2):\n\n" + rows,
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
            path = snapshot_spectrum(self._last_spectrum, self._snapshot_dir)
        except Exception as exc:  # noqa: BLE001 - report, keep window alive
            self._flash_status(f"Snapshot failed: {exc}")
            self.logger.error("Snapshot failed: %s", exc)
            return
        self._flash_status(f"Saved snapshot → {path}")
        self.logger.info("Saved snapshot → %s", path)

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
        width = self._sensor_width()
        try:
            result = session.fit(width)
        except CalibrationError as exc:
            self._flash_status(f"Calibration failed: {exc}")
            self.logger.error("Calibration failed: %s", exc)
            return

        if self._engine is not None:
            self._engine.set_calibration(result.wavelengths)
        saved = self._save_calibration(session)
        r2 = "" if result.r_squared is None else f", R²={result.r_squared:.5f}"
        tail = f" → {saved}" if saved else ""
        self._flash_status(
            f"Calibrated: {session.count} points, {result.order}-order fit{r2}{tail}"
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
        self._calib_mode = bool(on)
        self._flash_status(
            "Pick mode ON — click emission lines to add points, then press c."
            if on else "Pick mode off."
        )

    def _on_plot_click(self, x: float) -> None:
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

    def _save_calibration(self, session) -> str:
        if self.config is None:
            return ""
        try:
            path = session.save(self.config.get("calibration", "file"))
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

        engine = LiveEngine(source, self._params)
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
        self._last_peaks = [p.pixel for p in result.peaks]
        self._view.update_spectrum(spectrum, result)
        self._waterfall.update_spectrum(spectrum, result)
        self._dock.update_readouts(spectrum, result)
        if time.monotonic() >= self._status_hold_until:
            self.statusBar().showMessage(
                f"Live — {len(spectrum)} samples, {len(result.peaks)} peaks"
            )

    def _on_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Capture stopped: {message}")
        self.logger.error("Capture error: %s", message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._thread is not None:
            self._thread.stop()
            self._thread = None
        super().closeEvent(event)
