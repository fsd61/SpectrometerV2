"""Unit tests for the Qt-free live-view core (ui.live.LiveParams)."""

from ui.live import LiveParams


def test_savgol_order_clamps():
    p = LiveParams(savgol_order=3)
    p.adjust_savgol_order(50)
    assert p.savgol_order == 15
    p.adjust_savgol_order(-999)
    assert p.savgol_order == 0


def test_peak_min_dist_clamps():
    p = LiveParams(peak_min_dist=20)
    p.adjust_peak_min_dist(1000)
    assert p.peak_min_dist == 100
    p.adjust_peak_min_dist(-1000)
    assert p.peak_min_dist == 0


def test_threshold_steps_and_clamps():
    p = LiveParams(peak_thres=0.2)
    p.adjust_threshold(1)
    assert p.peak_thres == 0.25
    for _ in range(100):
        p.adjust_threshold(1)
    assert p.peak_thres == 1.0
    for _ in range(100):
        p.adjust_threshold(-1)
    assert p.peak_thres == 0.0


def test_toggles_return_new_state():
    p = LiveParams()
    assert p.toggle_hold_peaks() is True
    assert p.toggle_hold_peaks() is False
    assert p.toggle_measure() is True
    assert p.measure is True


def test_analyze_kwargs_match_pipeline_signature():
    p = LiveParams(savgol_window=17, savgol_order=4, peak_thres=0.3,
                   peak_min_dist=25, measure=True)
    assert p.analyze_kwargs() == {
        "savgol_window": 17, "savgol_order": 4, "peak_thres": 0.3,
        "peak_min_dist": 25, "measure": True,
    }


def test_measure_and_pixel_mode_are_mutually_exclusive():
    p = LiveParams()
    # Enabling measure clears pixel-mode, and vice-versa (mirrors recPixels).
    assert p.toggle_pixel_mode() is True
    assert p.pixel_mode is True and p.measure is False
    assert p.toggle_measure() is True
    assert p.measure is True and p.pixel_mode is False
    assert p.toggle_pixel_mode() is True
    assert p.pixel_mode is True and p.measure is False


def test_pixel_mode_does_not_change_analyze_kwargs():
    # Pixel-mode is a display concern only; it must not alter the analysis call.
    p = LiveParams()
    before = p.analyze_kwargs()
    p.toggle_pixel_mode()
    assert p.analyze_kwargs() == before
