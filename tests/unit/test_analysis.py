"""Unit tests for the extracted analysis module (Phase 3)."""

import numpy as np
import pytest

from analysis.smoothing import savitzky_golay
from analysis.peaks import peak_indexes


def test_savgol_requires_odd_window():
    with pytest.raises(TypeError):
        savitzky_golay(np.zeros(10), 4, 2)


def test_savgol_window_too_small_for_order():
    with pytest.raises(TypeError):
        savitzky_golay(np.zeros(10), 3, 3)


def test_savgol_preserves_length():
    y = np.random.default_rng(0).normal(size=101)
    assert savitzky_golay(y, 11, 3).shape == (101,)


def test_savgol_smooths_constant():
    assert np.allclose(savitzky_golay(np.full(50, 7.0), 7, 2), 7.0)


def test_peaks_flat_signal_returns_empty():
    assert len(peak_indexes(np.zeros(20))) == 0


def test_peaks_rejects_unsigned():
    with pytest.raises(ValueError):
        peak_indexes(np.arange(10, dtype=np.uint8))


def test_peaks_single_gaussian():
    x = np.arange(200.0)
    y = np.exp(-0.5 * ((x - 100) / 5.0) ** 2)
    pk = peak_indexes(y, thres=0.5, min_dist=5)
    assert len(pk) == 1 and abs(int(pk[0]) - 100) <= 1


def test_peaks_min_dist_merges_close_lines():
    x = np.arange(200.0)
    y = np.exp(-0.5 * ((x - 100) / 3.0) ** 2) + 0.9 * np.exp(-0.5 * ((x - 112) / 3.0) ** 2)
    assert len(peak_indexes(y, thres=0.2, min_dist=1)) >= 2
    assert len(peak_indexes(y, thres=0.2, min_dist=30)) == 1
