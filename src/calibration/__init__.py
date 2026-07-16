"""Calibration service: wavelength calibration, persistence, validation.

Fits and applies the pixel-to-wavelength mapping. Extracted from the baseline
and verified against golden data (Migration Plan Phase 3; DATA-002).
"""

from .wavelength import CalibrationResult, apply_calibration, calibrate, fit_calibration

__all__ = ["CalibrationResult", "apply_calibration", "calibrate", "fit_calibration"]
