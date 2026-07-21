"""Frequency-domain and multiresolution transforms (Migration Plan Phase 7 math).

Two optional analyses ported from the reference patch material
(`Docs/reference/Patch_-_Wtx_+_SA/`):

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
