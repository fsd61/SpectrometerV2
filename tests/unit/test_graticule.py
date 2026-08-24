"""Tests for the wavelength graticule marks (ui.graticule)."""

import numpy as np

from ui.graticule import marks, tens_and_fifties


def _linear_axis(lo=400.0, hi=700.0, n=601):
    return list(np.linspace(lo, hi, n))


def test_marks_land_on_whole_steps():
    axis = _linear_axis()
    found = marks(axis, 50)
    assert [nm for _p, nm in found] == [400, 450, 500, 550, 600, 650, 700]


def test_mark_pixels_are_correct_on_a_linear_axis():
    # 601 samples over 400-700 nm => 0.5 nm per pixel.
    axis = _linear_axis()
    found = dict((nm, p) for p, nm in marks(axis, 50))
    assert found[400] == 0
    assert found[500] == 200
    assert found[700] == 600


def test_marks_follow_a_non_linear_axis():
    """The whole point of locating marks on the real axis rather than lerping.

    A quadratic axis puts 500 nm well away from where a linear interpolation
    between the endpoints would place it; the mark must follow the data.
    """
    n = 1001
    pixels = np.arange(n, dtype=float)
    axis = 400.0 + 0.2 * pixels + 1.0e-4 * pixels**2   # 400 -> 700 nm, curved
    found = dict((nm, p) for p, nm in marks(list(axis), 50))
    true_pixel = int(np.argmin(np.abs(axis - 500.0)))
    assert found[500] == true_pixel
    # A linear read of the same span would be materially off.
    linear_guess = int(round((500.0 - axis[0]) / (axis[-1] - axis[0]) * (n - 1)))
    assert abs(linear_guess - true_pixel) > 50


def test_no_marks_without_a_calibration():
    assert marks([], 50) == []
    assert marks(None, 50) == []
    assert marks([550.0], 50) == []          # a single sample is not an axis


def test_marks_outside_the_range_are_not_pinned_to_the_edge():
    """A 552-648 nm axis reaches no whole 50 nm except 600."""
    axis = _linear_axis(552.0, 648.0, 193)
    assert [nm for _p, nm in marks(axis, 50)] == [600]


def test_descending_axis_is_handled():
    axis = _linear_axis(700.0, 400.0, 601)
    found = marks(axis, 50)
    assert [nm for _p, nm in found] == [400, 450, 500, 550, 600, 650, 700]
    # 400 nm now sits at the last pixel, not the first.
    assert dict((nm, p) for p, nm in found)[400] == 600


def test_tens_and_fifties_shapes_match_the_original():
    axis = _linear_axis()
    tens, fifties = tens_and_fifties(axis)
    assert all(isinstance(t, int) for t in tens)
    assert all(len(m) == 2 for m in fifties)
    # every 50 nm mark is also a 10 nm mark
    assert set(p for p, _nm in fifties) <= set(tens)
    assert len(tens) == 31          # 400..700 inclusive, every 10 nm
