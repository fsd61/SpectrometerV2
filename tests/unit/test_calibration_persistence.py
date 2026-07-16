"""Unit tests for calibration point persistence (Phase 6; DATA-002)."""

import pytest

from calibration.persistence import load_calibration_points, write_calibration_points
from errors import CalibrationError


def test_roundtrip(tmp_path):
    p = tmp_path / "caldata.txt"
    write_calibration_points(p, [35, 250, 470, 700], [404.66, 435.83, 546.07, 611.60])
    pixels, wavelengths = load_calibration_points(p)
    assert pixels == [35, 250, 470, 700]
    assert wavelengths == [404.66, 435.83, 546.07, 611.60]


def test_missing_file_raises(tmp_path):
    with pytest.raises(CalibrationError):
        load_calibration_points(tmp_path / "nope.txt")


def test_mismatched_counts_raise(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("1,2,3\r\n400,500\r\n")
    with pytest.raises(CalibrationError):
        load_calibration_points(p)


def test_too_few_lines_raise(tmp_path):
    p = tmp_path / "short.txt"
    p.write_text("1,2,3\r\n")
    with pytest.raises(CalibrationError):
        load_calibration_points(p)
