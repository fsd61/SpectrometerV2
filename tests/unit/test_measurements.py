"""Unit tests for FWHM / Gaussian-fit / noise / SNR measurements (Phase 3, TEST-002)."""

import numpy as np
import pytest

from analysis.measurements import (
    estimate_noise, estimate_snr, gaussian_fit, half_max_fwhm,
)

FACTOR = 2.0 * np.sqrt(2.0 * np.log(2.0))  # sigma -> FWHM


def _gauss(x, center, amp, sigma):
    return amp * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def test_half_max_fwhm_recovers_width():
    x = np.arange(400.0)
    y = _gauss(x, 200, 100, 10.0)             # sigma 10 -> FWHM 23.548
    assert half_max_fwhm(y, 200) == pytest.approx(FACTOR * 10.0, abs=0.5)


def test_half_max_requires_peak_above_baseline():
    with pytest.raises(ValueError):
        half_max_fwhm(np.zeros(10), 5)


def test_gaussian_fit_recovers_parameters():
    x = np.arange(400.0)
    y = 5.0 + _gauss(x, 180, 120, 8.0)
    fit = gaussian_fit(y, 180, window=30, baseline=5.0)
    assert fit.center == pytest.approx(180, abs=0.2)
    assert fit.amplitude == pytest.approx(120, rel=0.02)
    assert fit.sigma == pytest.approx(8.0, rel=0.02)
    assert fit.fwhm == pytest.approx(FACTOR * 8.0, rel=0.02)


def test_gaussian_fit_rejects_non_peak():
    with pytest.raises(ValueError):
        gaussian_fit(np.ones(50), 25)


def test_estimate_noise_matches_sigma():
    rng = np.random.default_rng(1)
    y = 10.0 + rng.normal(0.0, 4.0, size=2000)
    assert estimate_noise(y) == pytest.approx(4.0, rel=0.15)


def test_estimate_snr_matches_amplitude_over_noise():
    x = np.arange(800.0)
    rng = np.random.default_rng(2)
    y = 10.0 + _gauss(x, 400, 100.0, 8.0) + rng.normal(0.0, 5.0, size=800)
    assert estimate_snr(y, 400) == pytest.approx(100.0 / 5.0, rel=0.3)
