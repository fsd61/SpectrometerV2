"""Calibration point persistence (DATA-002).

Reads/writes the baseline ``caldata.txt`` format (two lines: pixel CSV, then
wavelength CSV), so calibrations remain interoperable with the original tool.
"""

from __future__ import annotations

from pathlib import Path

from errors import CalibrationError


def load_calibration_points(path: str | Path):
    """Return (pixels, wavelengths) parsed from a caldata file."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CalibrationError(f"cannot read calibration file: {path}") from exc
    if len(lines) < 2:
        raise CalibrationError("calibration file needs a pixel line and a wavelength line")
    try:
        pixels = [int(x) for x in lines[0].split(",") if x.strip()]
        wavelengths = [float(x) for x in lines[1].split(",") if x.strip()]
    except ValueError as exc:
        raise CalibrationError(f"invalid calibration data: {exc}") from exc
    if len(pixels) != len(wavelengths):
        raise CalibrationError("pixel and wavelength counts differ")
    return pixels, wavelengths


def write_calibration_points(path: str | Path, pixels, wavelengths) -> Path:
    """Write pixels/wavelengths in the baseline caldata format."""
    path = Path(path)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ",".join(str(p) for p in pixels) + "\r\n"
        + ",".join(str(w) for w in wavelengths) + "\r\n",
        encoding="utf-8",
    )
    return path
