"""Offscreen Qt widget tests (Migration Plan Phase 7, milestone 7).

These build the real PySide6 widgets under the ``offscreen`` platform, so they
exercise the Qt wiring the Qt-free core tests can't reach: action/shortcut
registration, menu/toolbar construction, and the click-to-calibrate handlers.

They ``importorskip`` PySide6/pyqtgraph and pytest-qt, so they skip cleanly
where Qt's system libraries aren't available (e.g. the headless CI sandbox) and
run wherever the ``[gui]`` extra is installed.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
pytest.importorskip("pytestqt")

from config.loader import load_config
from ui.live import LIVE_SHORTCUTS, LiveEngine, LiveParams, build_frame_source
from ui.qt.main_window import MainWindow
from ui.qt.spectrum_view import SpectrumView


@pytest.fixture
def window(qtbot):
    w = MainWindow(config=None)      # config=None => no capture thread started
    qtbot.addWidget(w)
    return w


def test_all_13_shortcuts_registered(window):
    for spec in LIVE_SHORTCUTS:
        act = window._actions.get(spec.key)
        assert act is not None, f"missing action for {spec.key}"
        assert act.shortcut().toString().lower().endswith(spec.key)
        assert hasattr(window, spec.handler)
    assert len(window._actions) == 13


def test_menus_and_toolbar_present(window):
    titles = [a.text() for a in window.menuBar().actions()]
    for expected in ("&File", "&Calibrate", "&Analysis", "&View", "&Help"):
        assert expected in titles
    assert len(window._toolbar.actions()) >= 5


def test_snapshot_with_no_frame_is_graceful(window):
    window.act_snapshot()
    assert "Nothing to snapshot" in window.statusBar().currentMessage()


def test_snapshot_confirmation_survives_the_live_counter(window, tmp_path):
    from analysis.pipeline import analyze
    from processing.spectrum import Spectrum

    window._snapshot_dir = str(tmp_path)
    spec = Spectrum(wavelengths=[], intensities=[1.0, 5.0, 2.0, 8.0, 3.0])
    window._last_spectrum = spec
    window.act_snapshot()
    assert "Saved snapshot" in window.statusBar().currentMessage()
    # A live frame arriving right after must not stomp the confirmation.
    result = analyze(spec.intensities, wavelengths=None, measure=False)
    window._on_frame(spec, result)
    assert "Saved snapshot" in window.statusBar().currentMessage()


def test_toggle_actions_track_params(window):
    m0 = window._params.measure
    window.act_toggle_measure()
    assert window._params.measure is (not m0)
    assert window._actions["m"].isChecked() == window._params.measure
    # Pixel-mode and measure are mutually exclusive; the checks must follow.
    window._params.measure = True
    window.act_toggle_pixel()
    assert window._params.pixel_mode is True and window._params.measure is False
    assert window._actions["p"].isChecked() is True
    assert window._actions["m"].isChecked() is False


def test_plot_click_gated_by_pick_mode(window):
    window._last_peaks = [100, 300, 500]
    window._on_plot_click(301.0)          # pick mode off -> ignored
    assert window._cal_session.count == 0


def test_click_to_calibrate_end_to_end(window, monkeypatch):
    from PySide6 import QtWidgets

    values = iter([405.0, 546.0, 611.0])
    monkeypatch.setattr(
        QtWidgets.QInputDialog, "getDouble",
        staticmethod(lambda *a, **k: (next(values), True)),
    )
    window._pick_action.setChecked(True)         # enter pick mode
    window._last_peaks = [100, 300, 500]
    for x in (101.0, 299.0, 498.0):              # snap to the three peaks
        window._on_plot_click(x)
    assert window._cal_session.count == 3
    assert window._cal_session.pixels() == [100, 300, 500]

    # Give the window a live engine to receive the applied calibration.
    src = build_frame_source(load_config(overrides=["camera.backend=synthetic"]))
    window._engine = LiveEngine(src, LiveParams())
    window.act_calibrate()
    assert window._engine.calibration is not None
    assert "Calibrated" in window.statusBar().currentMessage()


def test_calibrate_without_enough_points_reports(window):
    window._add_calibration_pick(100, 405.0)
    window.act_calibrate()
    assert "at least 3" in window.statusBar().currentMessage()


def test_spectrum_view_emits_and_updates(qtbot):
    view = SpectrumView()
    qtbot.addWidget(view)
    received = []
    view.plotClicked.connect(received.append)
    view.plotClicked.emit(123.0)                 # signal is wired and typed
    assert received == [123.0]
