"""Calibration service: wavelength calibration, persistence, validation.

Fits and applies the pixel-to-wavelength mapping and reads/writes calibration
points (baseline caldata format). Verified against golden data (Phase 3;
DATA-002).
"""

from .wavelength import CalibrationResult, apply_calibration, calibrate, fit_calibration
from .persistence import load_calibration_points, write_calibration_points

__all__ = [
    "CalibrationResult", "apply_calibration", "calibrate", "fit_calibration",
    "load_calibration_points", "write_calibration_points",
]
