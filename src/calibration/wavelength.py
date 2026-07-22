"""Wavelength calibration (Migration Plan Phase 3 extraction).

Extracts the scientific core of Les Wright's baseline ``readcal``: fit a
polynomial mapping sensor pixel -> wavelength (nm) and evaluate it per pixel.
The baseline used a 2nd-order fit for exactly three calibration points and a
3rd-order fit for more; that behavior is preserved and verified against
``tests/regression/golden/calibration.json``.

Human-readable status strings (the old ``calmsg`` UI text) are intentionally
NOT produced here — that is a presentation concern. This module returns only the
scientific result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from errors import CalibrationError


@dataclass
class CalibrationResult:
    """Result of a wavelength calibration fit."""

    coefficients: np.ndarray          # highest power first (np.polyfit convention)
    order: int                        # 2 or 3
    wavelengths: list[float]          # per-pixel wavelength (nm), rounded to 6 dp
    r_squared: Optional[float]        # goodness of fit (3rd-order only), else None


def fit_calibration(pixels: Sequence[float], wavelengths: Sequence[float]):
    """Fit the pixel->wavelength polynomial. Returns (coefficients, order)."""
    pixels = list(pixels)
    wavelengths = list(wavelengths)
    if len(pixels) != len(wavelengths):
        raise CalibrationError(
            f"calibration points mismatch: {len(pixels)} pixels vs "
            f"{len(wavelengths)} wavelengths"
        )
    if len(pixels) < 3:
        raise CalibrationError("at least 3 calibration points are required")
    order = 2 if len(pixels) == 3 else 3
    coefficients = np.polyfit(pixels, wavelengths, order)
    return coefficients, order


def apply_calibration(coefficients, width: int) -> list[float]:
    """Evaluate the polynomial for pixels [0, width), rounded to 6 dp.

    The 6-dp rounding matches the baseline exactly for byte-level regression.
    """
    values = np.polyval(coefficients, np.arange(width))
    return [round(float(v), 6) for v in values]


def calibrate(pixels, wavelengths, width: int) -> CalibrationResult:
    """Fit and evaluate a wavelength calibration over a sensor of ``width`` px."""
    coefficients, order = fit_calibration(pixels, wavelengths)
    wavelength_data = apply_calibration(coefficients, width)
    r_squared = None
    if order == 3:
        predicted = np.polyval(coefficients, np.asarray(pixels, dtype=float))
        corr = np.corrcoef(wavelengths, predicted)[0, 1]
        r_squared = float(corr ** 2)
    return CalibrationResult(coefficients, order, wavelength_data, r_squared)
