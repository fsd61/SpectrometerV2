"""Wavelet denoising and the raw-measurement rule (analysis.transforms, pipeline)."""

import numpy as np
import pytest

pytest.importorskip("pywt")

from analysis.linefit import fit_lines  # noqa: E402
from analysis.pipeline import analyze  # noqa: E402
from analysis.transforms import wavelet_denoise  # noqa: E402

X = np.arange(1280.0)
SIGMA = 4.0 / 2.3548
LINES = [(300.3, 80.0), (640.7, 25.0), (980.5, 120.0)]
TRUTH = 10 + sum(a * np.exp(-0.5 * ((X - c) / SIGMA) ** 2) for c, a in LINES)


def _noisy(seed, noise=3.0):
    return TRUTH + np.random.default_rng(seed).normal(0, noise, X.size)


def test_defaults_reduce_baseline_error_at_least_twofold():
    gains = []
    for seed in range(4):
        y = _noisy(seed)
        d = wavelet_denoise(y).denoised
        gains.append(np.std(y[400:600] - TRUTH[400:600]) / np.std(d[400:600] - TRUTH[400:600]))
    assert np.mean(gains) > 2.0


def test_defaults_do_not_move_lines():
    """Fitted centers on the denoised spectrum match those on the raw one.

    Compared frame by frame against the raw fit (not the truth), so ordinary
    noise scatter -- about +/-0.04 px for these lines -- cancels out and only a
    shift caused by denoising would show.
    """
    for seed in range(4):
        y = _noisy(seed)
        d = wavelet_denoise(y).denoised
        for c, a in LINES:
            on_raw = fit_lines(y, [round(c)], random_seed=0).lines[0]
            on_den = fit_lines(d, [round(c)], random_seed=0).lines[0]
            assert on_den.center_px == pytest.approx(on_raw.center_px, abs=0.1 if a < 50 else 0.03)
            if a > 50:
                assert on_den.amplitude / a > 0.9


def test_textbook_universal_soft_flattens_dim_lines():
    """Why the defaults are hard/0.6: universal soft halves a dim line."""
    soft, gentle = [], []
    for seed in range(4):
        y = _noisy(seed)
        c, a = LINES[1]
        soft.append(fit_lines(wavelet_denoise(y, threshold_scale=1.0, mode="soft").denoised,
                              [round(c)], random_seed=0).lines[0].amplitude / a)
        gentle.append(fit_lines(wavelet_denoise(y).denoised,
                                [round(c)], random_seed=0).lines[0].amplitude / a)
    assert np.mean(soft) < 0.6
    assert np.mean(gentle) > 0.85


def test_result_metadata_and_shape():
    r = wavelet_denoise(_noisy(0), wavelet="coif3", level=3, shifts=4)
    assert len(r.denoised) == X.size
    assert (r.wavelet, r.level, r.mode, r.shifts) == ("coif3", 3, "hard", 4)
    assert r.noise_sigma == pytest.approx(3.0, rel=0.2)
    assert r.threshold == pytest.approx(0.6 * r.noise_sigma * np.sqrt(2 * np.log(X.size)))


@pytest.mark.parametrize("kwargs", [{"mode": "medium"}, {"threshold_scale": -1}, {"level": 0}])
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        wavelet_denoise(_noisy(0), **kwargs)


def test_snr_is_measured_on_raw_data_not_the_denoised_trace():
    y = _noisy(1)
    d = wavelet_denoise(y).denoised
    raw = {p.pixel: p.snr for p in analyze(y, measure=True).peaks}
    honest = {p.pixel: p.snr for p in analyze(d, measure=True, measure_on=y).peaks}
    flattering = {p.pixel: p.snr for p in analyze(d, measure=True).peaks}
    px = min(raw, key=lambda p: abs(p - 980))
    assert honest[px] == pytest.approx(raw[px], rel=0.25)
    assert flattering[px] > 1.5 * raw[px]


def test_measure_on_must_match_length():
    with pytest.raises(ValueError):
        analyze([1.0] * 50, measure=True, measure_on=[1.0] * 49)
