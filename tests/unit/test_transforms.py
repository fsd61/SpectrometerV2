"""Unit tests for analysis.transforms (FFT + wavelet)."""

import numpy as np
import pytest

from analysis import fft_spectrum, wavelet_transform
from analysis.transforms import FftResult, WaveletResult

pywt = pytest.importorskip("pywt")  # wavelet tests need the optional dependency


def test_fft_recovers_known_frequency():
    # A pure sinusoid should peak at its own frequency bin.
    n = 512
    cycles = 8  # complete cycles across the window
    x = np.arange(n)
    y = np.sin(2 * np.pi * cycles * x / n)
    result = fft_spectrum(y, sample_spacing=1.0)
    assert isinstance(result, FftResult)
    # Ignore the DC bin; the dominant frequency is cycles/n.
    dominant = int(np.argmax(result.magnitudes[1:]) + 1)
    assert result.freqs[dominant] == pytest.approx(cycles / n, rel=1e-6)


def test_fft_dc_component_is_mean():
    y = np.full(64, 5.0)
    result = fft_spectrum(y)
    # Constant signal: all energy in the DC bin, equal to the mean.
    assert result.magnitudes[0] == pytest.approx(5.0)
    assert np.allclose(result.magnitudes[1:], 0.0, atol=1e-9)


def test_fft_rejects_empty_and_bad_spacing():
    with pytest.raises(ValueError):
        fft_spectrum([])
    with pytest.raises(ValueError):
        fft_spectrum([1, 2, 3], sample_spacing=0)


def test_wavelet_decomposition_reconstructs():
    y = np.linspace(0, 1, 256) + 0.1 * np.sin(np.linspace(0, 20, 256))
    result = wavelet_transform(y, wavelet="db4", level=4)
    assert isinstance(result, WaveletResult)
    assert result.level == 4
    assert result.details and result.approximation is result.coeffs[0]
    # Inverse transform should recover the original within numerical tolerance.
    reconstructed = pywt.waverec(result.coeffs, result.wavelet)
    assert np.allclose(reconstructed[: len(y)], y, atol=1e-9)


def test_wavelet_level_clamped_to_data_length():
    # 64 samples with db4 support at most level 3; requesting 4 must clamp.
    result = wavelet_transform(np.arange(64.0), wavelet="db4", level=4)
    assert result.level == 3


def test_wavelet_missing_dependency_message(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pywt":
            raise ImportError("no pywt")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"\[wavelet\]"):
        wavelet_transform(np.arange(16.0))
