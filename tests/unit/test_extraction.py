"""Unit tests for spectrum extraction (Phase 3)."""

import numpy as np
import pytest

from processing import Spectrum
from processing.extraction import extract_intensity, extract_spectrum, to_grayscale


def test_three_row_mean_truncates_to_uint8():
    g = np.zeros((7, 4))
    g[2] = [10, 20, 30, 40]
    g[3] = [10, 20, 30, 41]
    g[4] = [10, 20, 30, 42]
    out = extract_intensity(g, center_row=3)
    assert out.tolist() == [10, 20, 30, 41]   # (40+41+42)/3 = 41.0
    assert out.dtype == np.uint8


def test_default_center_is_frame_middle():
    height, width = 600, 20
    g = np.zeros((height, width))
    g[height // 2 - 1 : height // 2 + 2, :] = 100
    assert np.all(extract_intensity(g) == 100)


def test_constant_columns_recovered_as_uint8():
    prof = np.arange(50, dtype=float)
    g = np.tile(prof, (11, 1))
    assert np.array_equal(extract_intensity(g, center_row=5), prof.astype(np.uint8))


def test_uint8_truncation_of_fractional_mean():
    g = np.zeros((3, 1))
    g[0, 0], g[1, 0], g[2, 0] = 10, 10, 11     # mean 10.333 -> 10
    assert extract_intensity(g, center_row=1)[0] == 10


def test_average_window_out_of_bounds():
    with pytest.raises(ValueError):
        extract_intensity(np.zeros((3, 4)), center_row=0)


def test_average_rows_must_be_odd():
    with pytest.raises(ValueError):
        extract_intensity(np.zeros((10, 4)), average_rows=2)


def test_to_grayscale_passthrough_and_bgr_weights():
    assert to_grayscale(np.zeros((3, 3))).shape == (3, 3)
    bgr = np.zeros((1, 1, 3))
    bgr[..., 0], bgr[..., 1], bgr[..., 2] = 100, 150, 200
    assert to_grayscale(bgr)[0, 0] == pytest.approx(0.114 * 100 + 0.587 * 150 + 0.299 * 200)


def test_extract_spectrum_shape_and_metadata():
    g = np.tile(np.arange(64, dtype=float), (100, 1))
    sp = extract_spectrum(g, source="test")
    assert isinstance(sp, Spectrum)
    assert len(sp) == 64 and sp.wavelengths == []
    assert sp.metadata["center_row"] == 50
    assert sp.metadata["average_rows"] == 3
    assert sp.metadata["source"] == "test"
