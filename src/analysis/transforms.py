"""Frequency-domain and multiresolution transforms (Migration Plan Phase 7 math).

Two optional analyses ported from the original PySpectrometer2 patch
material:

* :func:`fft_spectrum` — a one-sided FFT magnitude spectrum. NumPy only, so it
  is always available.
* :func:`wavelet_transform` — a discrete wavelet decomposition via PyWavelets.
  ``pywt`` is an optional dependency (``pip install -e .[wavelet]``); it is
  imported lazily so importing this module never requires it.

Both return small, explicit result dataclasses rather than bare dicts so callers
get typed, documented fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


# --------------------------------------------------------------------------- #
# FFT (NumPy only)
# --------------------------------------------------------------------------- #
@dataclass
class FftResult:
    """One-sided FFT of a spectral intensity trace."""

    freqs: np.ndarray       # positive frequency bins (cycles per sample_spacing)
    magnitudes: np.ndarray  # one-sided magnitude spectrum, normalized by length
    full_fft: np.ndarray    # complex rfft result (retains phase information)


def fft_spectrum(intensity: Sequence[float], sample_spacing: float = 1.0) -> FftResult:
    """Compute the one-sided FFT magnitude spectrum of ``intensity``.

    Parameters
    ----------
    intensity:
        Raw intensity values from the spectrometer.
    sample_spacing:
        Spacing between samples, in pixels or nm. Frequency bins are reported in
        cycles per ``sample_spacing`` unit. Defaults to 1.0 (pixel units).

    Magnitudes are normalized by the sample count so amplitudes are comparable
    across traces of different length.
    """
    y = np.asarray(intensity, dtype=float)
    n = len(y)
    if n == 0:
        raise ValueError("intensity is empty")
    if sample_spacing <= 0:
        raise ValueError("sample_spacing must be positive")
    full = np.fft.rfft(y)
    return FftResult(
        freqs=np.fft.rfftfreq(n, d=sample_spacing),
        magnitudes=np.abs(full) / n,
        full_fft=full,
    )


# --------------------------------------------------------------------------- #
# Wavelet decomposition (optional PyWavelets dependency)
# --------------------------------------------------------------------------- #
@dataclass
class WaveletResult:
    """Discrete wavelet decomposition of a spectral intensity trace."""

    coeffs: list           # [cA_n, cD_n, ..., cD_1] (PyWavelets convention)
    approximation: np.ndarray  # low-frequency approximation at ``level``
    details: list          # detail (high-frequency) arrays, coarsest first
    wavelet: str
    level: int


def _import_pywt() -> Any:
    """Import PyWavelets lazily with an actionable error if it is missing."""
    try:
        import pywt  # noqa: WPS433 (intentional lazy import)
    except ImportError as exc:  # pragma: no cover - exercised via message test
        raise ImportError(
            "PyWavelets is required for the wavelet transform but is not "
            "installed. Install it with 'pip install -e .[wavelet]' (or "
            "'pip install PyWavelets')."
        ) from exc
    return pywt


def wavelet_transform(
    intensity: Sequence[float], wavelet: str = "db4", level: int = 4
) -> WaveletResult:
    """Perform a discrete wavelet decomposition of ``intensity``.

    Parameters
    ----------
    intensity:
        Raw intensity values.
    wavelet:
        PyWavelets wavelet name. Good choices for smooth spectral data:
        ``db4``, ``db6``, ``sym5``, ``coif3``. Defaults to ``db4``.
    level:
        Decomposition depth. ``4`` suits ~800-pixel data; reduce to 2-3 for
        shorter arrays. Clamped to the maximum the data length allows.
    """
    pywt = _import_pywt()
    y = np.asarray(intensity, dtype=float)
    if len(y) == 0:
        raise ValueError("intensity is empty")
    if level < 1:
        raise ValueError("level must be at least 1")
    max_level = pywt.dwt_max_level(len(y), pywt.Wavelet(wavelet).dec_len)
    used_level = min(level, max_level) if max_level >= 1 else 1
    coeffs = pywt.wavedec(y, wavelet, level=used_level)
    return WaveletResult(
        coeffs=coeffs,
        approximation=coeffs[0],
        details=coeffs[1:],
        wavelet=wavelet,
        level=used_level,
    )


# --------------------------------------------------------------------------- #
# Wavelet denoising (optional PyWavelets dependency)
# --------------------------------------------------------------------------- #
@dataclass
class WaveletDenoiseResult:
    """Outcome of :func:`wavelet_denoise`."""

    denoised: np.ndarray    # same length as the input
    noise_sigma: float      # noise estimated from the finest detail coefficients
    threshold: float        # absolute threshold applied to the detail coefficients
    wavelet: str
    level: int              # level actually used (clamped to the data length)
    mode: str               # 'soft' or 'hard'
    shifts: int             # cycle-spinning shifts averaged (1 = plain transform)


THRESHOLD_MODES = ("soft", "hard")


def wavelet_denoise(
    intensity: Sequence[float],
    wavelet: str = "sym5",
    level: int = 4,
    threshold_scale: float = 0.6,
    mode: str = "hard",
    shifts: int = 8,
) -> WaveletDenoiseResult:
    """Remove noise by thresholding wavelet detail coefficients.

    The noise level is estimated from the finest detail band (median absolute
    deviation / 0.6745) and every detail band is thresholded at the universal
    threshold ``threshold_scale * sigma * sqrt(2 ln N)`` (Donoho & Johnstone);
    the approximation band is kept. ``soft`` shrinks the surviving coefficients
    towards zero (smoother, slightly lowers peaks); ``hard`` keeps them as-is
    (preserves peak height, can leave small artefacts).

    Defaults (``hard``, ``0.6``) are deliberately gentler than the textbook
    universal soft threshold. Measured on simulated 4-px-wide lines with 3 counts
    of noise: universal soft cuts baseline noise 3.8x but leaves a dim (SNR ~8)
    line at 43% of its height with 3x worse center scatter; hard at 0.6 cuts
    noise 2.5x, keeps 93% of the height and leaves center precision unchanged.
    No setting makes fitted line centers *more* precise than fitting the raw
    data -- denoising cannot add information -- so use it to clean the display
    and peak detection, and fit or measure lines on the raw spectrum.

    A plain discrete wavelet transform is not shift-invariant, so the result
    depends on where a line falls relative to the dyadic grid, and asymmetric
    families can pull a line's apparent center. ``shifts`` > 1 applies cycle
    spinning (Coifman & Donoho): the spectrum is denoised at that many circular
    shifts and the un-shifted results are averaged, which removes most of that
    dependence. Symmetric-ish families (``sym5``, ``coif3``) are preferred for
    line positions.
    """
    pywt = _import_pywt()
    y = np.asarray(intensity, dtype=float)
    n = len(y)
    if n == 0:
        raise ValueError("intensity is empty")
    if mode not in THRESHOLD_MODES:
        raise ValueError(f"mode must be one of {THRESHOLD_MODES}, got {mode!r}")
    if threshold_scale < 0:
        raise ValueError("threshold_scale must be >= 0")
    if level < 1:
        raise ValueError("level must be at least 1")
    shifts = max(1, int(shifts))
    max_level = pywt.dwt_max_level(n, pywt.Wavelet(wavelet).dec_len)
    used_level = min(level, max_level) if max_level >= 1 else 1

    finest = pywt.wavedec(y, wavelet, level=1)[-1]
    sigma = float(np.median(np.abs(finest)) / 0.6745)
    threshold = float(threshold_scale * sigma * np.sqrt(2.0 * np.log(max(n, 2))))

    acc = np.zeros(n)
    for k in range(shifts):
        shifted = np.roll(y, k)
        coeffs = pywt.wavedec(shifted, wavelet, level=used_level)
        coeffs = [coeffs[0]] + [pywt.threshold(d, threshold, mode=mode) for d in coeffs[1:]]
        acc += np.roll(pywt.waverec(coeffs, wavelet)[:n], -k)
    return WaveletDenoiseResult(
        denoised=acc / shifts, noise_sigma=sigma, threshold=threshold,
        wavelet=wavelet, level=used_level, mode=mode, shifts=shifts,
    )
