"""End-to-end 1-D spectral analysis (Migration Plan Phase 3).

Ties the extracted primitives together: Savitzky–Golay smoothing then peak
detection, with optional pixel->wavelength mapping. Pure and platform-neutral;
consumes intensities (or a Spectrum) and an optional wavelength axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from .peaks import peak_indexes
from .smoothing import savitzky_golay


@dataclass
class Peak:
    """A detected spectral line."""

    pixel: int
    intensity: float
    wavelength: Optional[float] = None  # nm, if a calibration was supplied


@dataclass
class SpectralAnalysis:
    """Result of :func:`analyze`."""

    smoothed: List[float]
    peaks: List[Peak] = field(default_factory=list)


def analyze(
    intensities: Sequence[float],
    wavelengths: Optional[Sequence[float]] = None,
    savgol_window: int = 17,
    savgol_order: int = 3,
    peak_thres: float = 0.2,
    peak_min_dist: int = 20,
) -> SpectralAnalysis:
    """Smooth, detect peaks, and (optionally) assign wavelengths.

    Args:
        intensities: raw 1-D intensity samples (e.g. ``Spectrum.intensities``).
        wavelengths: optional per-pixel wavelength axis (from calibration).
        savgol_window / savgol_order: smoothing parameters.
        peak_thres / peak_min_dist: peak-detection parameters.

    Returns:
        :class:`SpectralAnalysis` with the smoothed trace and detected peaks.
    """
    y = np.asarray(intensities, dtype=float)
    smoothed = savitzky_golay(y, savgol_window, savgol_order)
    indices = [int(i) for i in peak_indexes(smoothed, thres=peak_thres, min_dist=peak_min_dist)]

    have_wl = wavelengths is not None and len(wavelengths) >= len(smoothed)
    peaks = [
        Peak(
            pixel=i,
            intensity=float(smoothed[i]),
            wavelength=float(wavelengths[i]) if have_wl else None,
        )
        for i in indices
    ]
    return SpectralAnalysis(smoothed=[float(v) for v in smoothed], peaks=peaks)
