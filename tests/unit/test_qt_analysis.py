"""Offscreen tests for the Analysis panel and its main-window wiring."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
pytest.importorskip("pytestqt")

from cameras.synthetic_camera import OV9281_DEMO_LINES, ov9281_demo_camera  # noqa: E402
from ui.live import LIVE_SHORTCUTS, CameraFrameSource, LiveEngine  # noqa: E402
from ui.qt.main_window import MainWindow  # noqa: E402

LAW = lambda px: 600.0 + 0.266 * px + 2e-6 * px ** 2  # noqa: E731


@pytest.fixture
def window(qtbot):
    w = MainWindow(config=None)      # no capture thread; frames are fed by hand
    qtbot.addWidget(w)
    yield w
    if w._worker is not None:
        w._worker.wait(20000)


def _feed_frame(window, rows=3, precision="integer", denoise=False):
    cam = ov9281_demo_camera(seed=0)
    cam.initialize()
    source = CameraFrameSource(cam, average_rows=rows, precision=precision)
    window._wavelet.denoise = denoise
    engine = LiveEngine(source, window._params, wavelet=window._wavelet)
    window._engine = engine
    window._source = source
    window._analysis.set_extraction_source(True, rows, precision)
    spectrum, result = engine.step()
    window._on_frame(spectrum, result)
    return source


def test_original_shortcuts_untouched_and_new_ones_added(window):
    assert len(window._actions) == len(LIVE_SHORTCUTS) == 13
    for key in ("w", "f"):
        assert window._extra_actions[key].shortcut().toString().lower() == key
    assert {"use_fitted", "compare", "clear_fit"} <= set(window._extra_actions)


def test_analysis_panel_is_a_tab_beside_controls(window):
    assert window._analysis.windowTitle() == "Analysis"
    assert window._analysis in window.tabifiedDockWidgets(window._dock)


def test_denoise_action_and_checkbox_stay_in_sync(window):
    window._extra_actions["w"].setChecked(True)
    assert window._wavelet.denoise is True
    assert window._analysis._denoise.isChecked()
    window._analysis._denoise.setChecked(False)
    assert window._wavelet.denoise is False
    assert not window._extra_actions["w"].isChecked()


def test_fit_mode_and_pick_mode_are_exclusive(window):
    window._set_fit_mode(True)
    window._pick_action.setChecked(True)
    assert window._calib_mode and not window._fit_mode
    window._set_fit_mode(True)
    assert window._fit_mode and not window._calib_mode


def test_extraction_controls_disabled_without_a_camera(window):
    assert not window._analysis._height.isEnabled()


def test_extraction_controls_drive_the_live_source(window):
    source = _feed_frame(window)
    assert window._analysis._height.isEnabled()
    window._analysis.extractionChanged.emit(301, "float")
    assert (source.average_rows, source.precision) == (301, "float")
    window._analysis.extractionChanged.emit(1001, "float")      # taller than the frame
    assert source.average_rows == 301
    assert window._analysis._height.value() == 301


def test_raw_overlay_drawn_only_when_denoising(window):
    pytest.importorskip("pywt")
    _feed_frame(window, denoise=False)
    assert window._view._raw.getData()[0] is None or len(window._view._raw.getData()[0]) == 0
    _feed_frame(window, denoise=True)
    assert len(window._view._raw.getData()[0]) == 1280
    assert "removed" in window._analysis._noise_lbl.text()


def test_click_fits_the_doublet_in_the_background(window, qtbot):
    _feed_frame(window, rows=101, precision="float")
    window._analysis._n_lines.setValue(2)
    window._set_fit_mode(True)
    window._on_plot_click(702.0)
    qtbot.waitUntil(lambda: window._last_fit is not None, timeout=30000)
    fit, _wl, source = window._last_fit
    assert source == "raw"
    assert fit.lines[0].center_px == pytest.approx(700.0, abs=0.2)
    assert fit.lines[1].center_px == pytest.approx(704.4, abs=0.2)
    assert window._view.fit_item_count() == 3            # model + 2 components
    assert window._analysis._fit_table.rowCount() == 2
    window.act_clear_fit()
    assert window._view.fit_item_count() == 0


def test_compare_needs_four_lines(window):
    _feed_frame(window)
    for c, _a, _w in OV9281_DEMO_LINES[:3]:
        window._add_calibration_pick(round(c), LAW(c))
    window.act_compare_centroids()
    assert "at least 4" in window.statusBar().currentMessage()


def test_compare_centroid_methods_end_to_end(window, qtbot):
    _feed_frame(window, rows=101, precision="float")
    for c, _a, _w in OV9281_DEMO_LINES:
        window._add_calibration_pick(round(c), LAW(c))
    window.act_compare_centroids()
    qtbot.waitUntil(lambda: window._last_comparison is not None, timeout=60000)
    comp = window._last_comparison
    assert len(comp.rows) == len(OV9281_DEMO_LINES)
    assert comp.rms_fitted < comp.rms_pick
    assert window._comparison_dialog.isVisible()
    window._comparison_dialog.close()


def test_calibration_from_fitted_centers(window, qtbot):
    _feed_frame(window, rows=101, precision="float")
    for c, _a, _w in OV9281_DEMO_LINES:
        window._add_calibration_pick(round(c), LAW(c))
    window._set_use_fitted(True)
    window.act_calibrate()
    qtbot.waitUntil(lambda: window._engine.calibration is not None, timeout=60000)
    axis = window._engine.calibration
    # The fitted-center calibration reproduces the true law at the doublet.
    assert axis[704] == pytest.approx(LAW(704), abs=0.02)
    assert "fitted centers" in window.statusBar().currentMessage()
