"""Line-shape and noise measurements (Migration Plan Phase 3; TEST-002).

New scientific capability the baseline lacked: FWHM, amplitude via a Gaussian
fit, noise estimation, and SNR. All dependency-free (NumPy only) — the Gaussian
fit uses a log-parabola least-squares rather than SciPy's ``curve_fit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .smoothing import savitzky_golay

_FWHM_FACTOR = 2.0 * np.sqrt(2.0 * np.log(2.0))  # sigma -> FWHM


@dataclass
class GaussianFit:
    center: float      # sub-pixel center
    amplitude: float   # peak height above baseline
    sigma: float
    fwhm: float        # in samples


def half_max_fwhm(y: Sequence[float], peak_index: int, baseline: Optional[float] = None) -> float:
    """Full width at half maximum around ``peak_index``, by interpolated
    half-max crossings. Returns width in samples.
    """
    y = np.asarray(y, dtype=float)
    peak_index = int(peak_index)
    if baseline is None:
        baseline = float(np.min(y))
    peak_val = float(y[peak_index])
    if peak_val <= baseline:
        raise ValueError("peak is not above the baseline")
    half = baseline + (peak_val - baseline) / 2.0

    left = peak_index
    while left > 0 and y[left] > half:
        left -= 1
    left_x = float(left) if y[left] > half else left + (half - y[left]) / (y[left + 1] - y[left])

    right = peak_index
    n = len(y)
    while right < n - 1 and y[right] > half:
        right += 1
    right_x = float(right) if y[right] > half else (right - 1) + (half - y[right - 1]) / (y[right] - y[right - 1])

    return right_x - left_x


def gaussian_fit(y: Sequence[float], peak_index: int, window: int = 10,
                 baseline: Optional[float] = None, min_fraction: float = 0.1) -> GaussianFit:
    """Estimate a Gaussian's center/amplitude/sigma/FWHM near ``peak_index``.

    Uses a log-parabola fit: for a Gaussian, ``ln(y - baseline)`` is a parabola,
    so a quadratic ``polyfit`` recovers the parameters without SciPy. Only the
    line *core* is fitted — samples within ``window`` whose height exceeds
    ``min_fraction`` of the peak height — which keeps narrow lines accurate and
    rejects baseline/noise and neighboring lines.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    peak_index = int(peak_index)
    if baseline is None:
        baseline = float(np.min(y))
    peak_amp = float(y[peak_index]) - baseline
    if peak_amp <= 0:
        raise ValueError("peak is not above the baseline")
    lo, hi = max(0, peak_index - window), min(n, peak_index + window + 1)
    xs = np.arange(lo, hi, dtype=float)
    ys = y[lo:hi] - baseline
    mask = ys > max(0.0, min_fraction * peak_amp)
    xs, ys = xs[mask], ys[mask]
    if len(xs) < 3:
        raise ValueError("insufficient core samples for a Gaussian fit")
    a, b, c = np.polyfit(xs, np.log(ys), 2)
    if a >= 0:
        raise ValueError("fitted parabola is not concave (not a peak)")
    center = -b / (2 * a)
    sigma = float(np.sqrt(-1.0 / (2 * a)))
    amplitude = float(np.exp(c - b * b / (4 * a)))
    return GaussianFit(center=float(center), amplitude=amplitude, sigma=sigma,
                       fwhm=float(_FWHM_FACTOR * sigma))


def estimate_noise(y: Sequence[float], window: int = 17, order: int = 3) -> float:
    """Robust noise sigma from the high-frequency residual (y - smoothed),
    via the median absolute deviation. Works even with signal present.
    """
    y = np.asarray(y, dtype=float)
    if len(y) < window:
        return float(np.std(y))
    residual = y - savitzky_golay(y, window, order)
    mad = float(np.median(np.abs(residual - np.median(residual))))
    return mad / 0.6745 if mad > 0 else float(np.std(residual))


def estimate_snr(y: Sequence[float], peak_index: Optional[int] = None,
                 baseline: Optional[float] = None, noise: Optional[float] = None) -> float:
    """Signal-to-noise ratio: (signal above baseline) / noise sigma."""
    y = np.asarray(y, dtype=float)
    if baseline is None:
        baseline = float(np.median(y))
    if noise is None:
        noise = estimate_noise(y)
    if noise <= 0:
        raise ValueError("noise estimate must be positive")
    signal = (float(y[int(peak_index)]) if peak_index is not None else float(np.max(y))) - baseline
    return signal / noise
