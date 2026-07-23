"""Tests for the Qt-free click-to-calibrate core (M6): CalibrationSession and
the peak-snap helper. No Qt, no display."""

import pytest

from calibration.persistence import load_calibration_points
from errors import CalibrationError
from ui.live import CalibrationSession, snap_pixel_to_peak


def test_session_collects_and_reports_points():
    s = CalibrationSession()
    assert s.count == 0 and s.ready is False
    s.add(100, 405.0)
    s.add(300.4, 546.0)          # pixel rounded
    assert s.pixels() == [100, 300]
    assert s.wavelengths() == [405.0, 546.0]
    assert s.ready is False       # need >= 3
    s.add(500, 611.0)
    assert s.ready is True and s.count == 3


def test_remove_last_and_clear():
    s = CalibrationSession()
    for p, w in [(100, 405.0), (300, 546.0)]:
        s.add(p, w)
    s.remove_last()
    assert s.pixels() == [100]
    s.clear()
    assert s.count == 0


def test_fit_order_2_for_three_points_3_for_more():
    s = CalibrationSession()
    for p, w in [(100, 405.0), (300, 546.0), (500, 611.0)]:
        s.add(p, w)
    r3 = s.fit(800)
    assert r3.order == 2 and len(r3.wavelengths) == 800
    s.add(650, 700.0)
    assert s.fit(800).order == 3


def test_fit_below_three_points_raises():
    s = CalibrationSession()
    s.add(100, 405.0)
    s.add(300, 546.0)
    with pytest.raises(CalibrationError):
        s.fit(800)


def test_axis_is_monotonic_for_ordered_points():
    s = CalibrationSession()
    for p, w in [(50, 400.0), (400, 550.0), (750, 700.0)]:
        s.add(p, w)
    axis = s.axis(800)
    assert axis[0] < axis[400] < axis[-1]


def test_save_round_trips_through_baseline_format(tmp_path):
    s = CalibrationSession()
    pts = [(100, 405.0), (300, 546.0), (500, 611.0)]
    for p, w in pts:
        s.add(p, w)
    path = s.save(tmp_path / "caldata.txt")
    pixels, wavelengths = load_calibration_points(path)
    assert pixels == [100, 300, 500]
    assert wavelengths == [405.0, 546.0, 611.0]


def test_snap_pixel_to_peak():
    peaks = [100, 300, 500]
    assert snap_pixel_to_peak(303.2, peaks) == 300     # within tol -> snap
    assert snap_pixel_to_peak(340, peaks) == 340       # beyond tol -> keep
    assert snap_pixel_to_peak(340, peaks, tol=50) == 300
    assert snap_pixel_to_peak(42.6, []) == 43          # no peaks -> rounded click
