"""Calibration service: wavelength calibration, persistence, validation.

Fits and applies the pixel-to-wavelength mapping and reads/writes calibration
points (baseline caldata format). Verified against golden data (Phase 3;
DATA-002). Slit width from laser diffraction lives in :mod:`calibration.slit`.
"""

from .wavelength import CalibrationResult, apply_calibration, calibrate, fit_calibration
from .persistence import load_calibration_points, write_calibration_points
from .slit import (
    DialCalibration, SlitWidthResult, fit_dial_calibration,
    fit_dial_calibration_from_results, fringe_positions_mm, measure_slit_width,
)

__all__ = [
    "CalibrationResult", "apply_calibration", "calibrate", "fit_calibration",
    "load_calibration_points", "write_calibration_points",
    "DialCalibration", "SlitWidthResult", "fit_dial_calibration",
    "fit_dial_calibration_from_results", "fringe_positions_mm", "measure_slit_width",
]
