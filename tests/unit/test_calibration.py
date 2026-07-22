"""Unit tests for the extracted calibration module (Phase 3)."""

import pytest

from calibration.wavelength import apply_calibration, calibrate, fit_calibration
from errors import CalibrationError


def test_three_points_use_second_order():
    coeffs, order = fit_calibration([0, 400, 800], [380, 560, 750])
    assert order == 2 and len(coeffs) == 3


def test_more_points_use_third_order():
    _, order = fit_calibration([0, 200, 400, 600, 800], [380, 450, 540, 650, 760])
    assert order == 3


def test_mismatched_lengths_raise():
    with pytest.raises(CalibrationError):
        fit_calibration([0, 400, 800], [380, 560])


def test_too_few_points_raise():
    with pytest.raises(CalibrationError):
        fit_calibration([0, 800], [380, 750])


def test_apply_length_and_monotonic():
    res = calibrate([0, 400, 800], [380, 560, 750], 800)
    assert len(res.wavelengths) == 800
    assert res.wavelengths[0] == pytest.approx(380, abs=1e-6)
    assert res.wavelengths[-1] > res.wavelengths[0]


def test_calibration_recovers_reference_points():
    res = calibrate([0, 400, 800], [380.0, 560.0, 750.0], 801)
    assert res.wavelengths[0] == pytest.approx(380.0, abs=1e-4)
    assert res.wavelengths[400] == pytest.approx(560.0, abs=1e-4)
    assert res.wavelengths[800] == pytest.approx(750.0, abs=1e-4)
