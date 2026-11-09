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
    from ui.qt.reference_line_dialog import ReferenceLineDialog

    values = iter([405.0, 546.0, 611.0])
    monkeypatch.setattr(
        ReferenceLineDialog, "get_wavelength",
        classmethod(lambda cls, *a, **k: (next(values), True, "Hg I")),
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
    assert window._ref_species == "Hg I"         # remembered for the next click


def test_pick_on_calibrated_axis_uses_pixels(window, monkeypatch):
    """On a calibrated plot the click x is in nm: it must be converted to a
    pixel before snapping, and the dialog gets that pixel's wavelength."""
    from processing.spectrum import Spectrum
    from ui.qt.reference_line_dialog import ReferenceLineDialog

    seen = {}

    def fake(cls, parent, pixel, estimate_nm=None, species=None):
        seen.update(pixel=pixel, estimate=estimate_nm)
        return 811.531, True, "Ar I"

    monkeypatch.setattr(ReferenceLineDialog, "get_wavelength", classmethod(fake))
    wl = [600.0 + 0.266 * i for i in range(1280)]
    window._last_spectrum = Spectrum(wavelengths=wl, intensities=[0.0] * 1280)
    window._last_peaks = [793]
    window._pick_action.setChecked(True)
    window._on_plot_click(wl[790])               # near-miss click, in nm
    assert seen["pixel"] == 793                  # snapped in pixel space
    assert abs(seen["estimate"] - wl[793]) < 1e-9
    assert window._cal_session.pixels() == [793]


def test_reference_line_dialog_lists_argon(qtbot):
    from ui.qt.reference_line_dialog import ReferenceLineDialog

    dialog = ReferenceLineDialog(700, species="Ar I")
    qtbot.addWidget(dialog)
    assert dialog.species() == "Ar I"
    assert dialog._list.count() > 20
    # Uncalibrated: strongest first, and selecting fills the value box.
    assert "811.531" in dialog._list.item(0).text() or "912.297" in dialog._list.item(0).text()
    from PySide6 import QtCore

    dialog._list.setCurrentRow(3)
    expected = dialog._list.item(3).data(QtCore.Qt.ItemDataRole.UserRole)
    assert dialog.wavelength() == expected       # full NIST precision, not the rounded box
    dialog._value.setValue(700.25)               # typing still wins
    assert dialog.wavelength() == pytest.approx(700.25)


def test_reference_line_dialog_nearest_first_when_calibrated(qtbot):
    from ui.qt.reference_line_dialog import ReferenceLineDialog

    dialog = ReferenceLineDialog(793, estimate_nm=811.2, species="Ar I")
    qtbot.addWidget(dialog)
    assert "811.531" in dialog._list.item(0).text()
    assert "Δ +0.33 nm" in dialog._list.item(0).text()
    assert abs(dialog.wavelength() - 811.53109) < 1e-4


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


def _calibrated_argon_frame(window):
    """A calibrated frame with an Ar 811.531 nm line, as the window last saw it."""
    import numpy as np

    from processing.spectrum import Spectrum

    wl = [600.0 + 0.266 * i for i in range(1280)]
    center = (811.531 - 600.0) / 0.266                   # 795.23 px
    x = np.arange(1280, dtype=float)
    y = 5.0 + 900.0 * np.exp(-0.5 * ((x - center) / 1.7) ** 2)
    window._last_spectrum = Spectrum(wavelengths=wl, intensities=list(y))
    window._last_peaks = [795]
    return wl, center


def test_identify_mode_lists_argon(window):
    wl, center = _calibrated_argon_frame(window)
    window._extra_actions["n"].setChecked(True)          # key n
    assert window._identify_mode and window._analysis._identify_btn.isChecked()
    window._on_plot_click(wl[797])                       # near miss, in nm
    measured, position = window._last_identified
    assert position == pytest.approx(center, abs=0.1)
    assert measured == pytest.approx(811.531, abs=0.03)
    table = window._analysis._id_table
    assert table.rowCount() >= 1
    assert table.item(0, 0).text() == "Ar I"
    assert table.item(0, 1).text() == "811.531 nm"
    assert "Ar I 811.531" in window.statusBar().currentMessage()


def test_identify_follows_element_choice(window):
    wl, _ = _calibrated_argon_frame(window)
    window._set_identify_mode(True)
    window._on_plot_click(wl[795])
    window._analysis._species_boxes["Ar I"].setChecked(False)   # re-runs at once
    texts = [window._analysis._id_table.item(r, 0).text()
             for r in range(window._analysis._id_table.rowCount())]
    assert "Ar I" not in texts


def test_identify_needs_calibration(window):
    window._set_identify_mode(True)
    window._on_plot_click(300.0)
    assert "calibrated" in window.statusBar().currentMessage()
    assert window._last_identified is None


def test_click_modes_are_exclusive(window):
    window._set_identify_mode(True)
    window._set_fit_mode(True)
    assert window._fit_mode and not window._identify_mode
    assert not window._extra_actions["n"].isChecked()
    window._set_identify_mode(True)
    assert window._identify_mode and not window._fit_mode
    window._pick_action.setChecked(True)
    assert window._calib_mode and not window._identify_mode
