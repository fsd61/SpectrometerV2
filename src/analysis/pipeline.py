"""End-to-end 1-D spectral analysis (Migration Plan Phase 3).

Ties the extracted primitives together: Savitzky–Golay smoothing, peak
detection, optional pixel->wavelength mapping, and optional per-peak shape/SNR
measurement. Pure and platform-neutral.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from .peaks import peak_indexes
from .smoothing import savitzky_golay
from .measurements import estimate_noise, estimate_snr, gaussian_fit, half_max_fwhm


@dataclass
class Peak:
    """A detected spectral line."""

    pixel: int
    intensity: float
    wavelength: Optional[float] = None  # nm, if a calibration was supplied
    fwhm: Optional[float] = None        # pixels (measure=True)
    fwhm_nm: Optional[float] = None     # nm, if calibrated + measured
    snr: Optional[float] = None


@dataclass
class SpectralAnalysis:
    """Result of :func:`analyze`."""

    smoothed: List[float]
    peaks: List[Peak] = field(default_factory=list)
    noise: Optional[float] = None
    # Set by the live engine when wavelet denoising fed the analysis: the
    # denoised series (``smoothed`` is then derived from it, while the raw
    # spectrum stays untouched in the Spectrum). None when denoising is off.
    denoised: Optional[List[float]] = None


def _dispersion_nm_per_px(wavelengths, i):
    n = len(wavelengths)
    lo, hi = max(0, i - 1), min(n - 1, i + 1)
    if hi == lo:
        return None
    return abs(wavelengths[hi] - wavelengths[lo]) / (hi - lo)


def analyze(
    intensities: Sequence[float],
    wavelengths: Optional[Sequence[float]] = None,
    savgol_window: int = 17,
    savgol_order: int = 3,
    peak_thres: float = 0.2,
    peak_min_dist: int = 20,
    measure: bool = False,
    measure_window: int = 12,
    measure_on: Optional[Sequence[float]] = None,
) -> SpectralAnalysis:
    """Smooth, detect peaks, and optionally assign wavelengths and measure shape.

    When ``measure`` is True, each peak also gets FWHM (Gaussian fit of the raw
    intensities, falling back to a half-max width) and an SNR estimate; FWHM in
    nm is added when a wavelength axis is supplied.

    ``measure_on`` (same length) is the series FWHM and SNR are measured on;
    it defaults to ``intensities``. Pass the raw spectrum when ``intensities``
    has been denoised, so line widths and SNR are not flattered by the
    denoising: a denoised trace has artificially low noise.
    """
    y = np.asarray(intensities, dtype=float)
    y_meas = y if measure_on is None else np.asarray(measure_on, dtype=float)
    if len(y_meas) != len(y):
        raise ValueError("measure_on must be the same length as intensities")
    smoothed = savitzky_golay(y, savgol_window, savgol_order)
    indices = [int(i) for i in peak_indexes(smoothed, thres=peak_thres, min_dist=peak_min_dist)]

    have_wl = wavelengths is not None and len(wavelengths) >= len(smoothed)
    noise = estimate_noise(y_meas) if measure else None
    baseline = float(np.median(y_meas)) if measure else None

    peaks: List[Peak] = []
    for i in indices:
        peak = Peak(
            pixel=i,
            intensity=float(smoothed[i]),
            wavelength=float(wavelengths[i]) if have_wl else None,
        )
        if measure:
            try:
                fit = gaussian_fit(y_meas, i, window=measure_window, baseline=baseline)
                peak.fwhm = fit.fwhm
            except (ValueError, np.linalg.LinAlgError):
                try:
                    peak.fwhm = half_max_fwhm(y_meas, i, baseline=baseline)
                except ValueError:
                    peak.fwhm = None
            peak.snr = estimate_snr(y_meas, i, baseline=baseline, noise=noise)
            if peak.fwhm is not None and have_wl:
                disp = _dispersion_nm_per_px(wavelengths, i)
                if disp is not None:
                    peak.fwhm_nm = peak.fwhm * disp
        peaks.append(peak)

    return SpectralAnalysis(smoothed=[float(v) for v in smoothed], peaks=peaks, noise=noise)
