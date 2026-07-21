"""Configuration schema (CFG-004: every key documented with purpose/valid options).

The schema is the single source of truth for configuration: the set of valid
sections and keys, their types, defaults, permitted values/ranges, and human
documentation. The loader validates INI input against this schema and the
docs are rendered by ``spectrometerv2 describe-config``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class Field:
    """One configuration key definition."""

    type: str                       # "str" | "int" | "float" | "bool" | "path"
    default: Any
    doc: str
    choices: Optional[Sequence[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None


# NOTE: Keep this aligned with the Requirements doc. Synthetic-generator keys
# mirror SYN-002..SYN-007; lorentzian/voigt are declared here but only gaussian
# is implemented initially (SYN-007 marks the others as future extensions).
SCHEMA: dict[str, dict[str, Field]] = {
    "general": {
        "platform": Field(
            "str", "auto",
            "Target platform hint. 'auto' detects at runtime.",
            choices=["auto", "linux", "windows", "raspberrypi"],
        ),
    },
    "logging": {
        "level": Field(
            "str", "INFO", "Minimum log level.",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        ),
        "directory": Field("path", "logs", "Directory for rotating log files (LOG-002)."),
        "max_bytes": Field("int", 1_048_576, "Max bytes per log file before rotation.", min=1024),
        "backup_count": Field("int", 5, "Number of rotated log files to retain.", min=0),
        "console": Field("bool", True, "Also emit logs to stderr."),
    },
    "camera": {
        "backend": Field(
            "str", "auto",
            "Camera source. 'auto' picks the CSI (Pi ribbon) camera or a USB "
            "camera; 'csi' = Pi ribbon camera; 'usb' = USB/webcam; 'synthetic' = "
            "simulated data (clearly labelled); 'none' = no camera. "
            "('picamera2' is accepted as an alias for 'csi'.)",
            choices=["auto", "usb", "csi", "picamera2", "synthetic", "none"],
        ),
        "on_missing": Field(
            "str", "prompt",
            "When 'auto' finds no camera: 'prompt' asks (only in an interactive "
            "terminal; otherwise behaves like 'error'), 'error' exits with guidance, "
            "'synthetic' falls back to simulated data with a warning.",
            choices=["prompt", "error", "synthetic"],
        ),
        "device_index": Field("int", 0, "Index of the camera device.", min=0),
        "width": Field("int", 1920, "Requested frame width in pixels.", min=1),
        "height": Field("int", 1080, "Requested frame height in pixels.", min=1),
    },
    "processing": {
        "slice_row": Field(
            "int", -1,
            "Sensor row used for the 1-D spectral slice; -1 = auto/center.",
            min=-1,
        ),
    },
    "calibration": {
        "file": Field("path", "config/calibration.json", "Path to the saved wavelength calibration."),
    },
    "synthetic": {
        "wavelength_min": Field("float", 380.0, "Lower wavelength bound, nm (SYN-006).", min=0.0),
        "wavelength_max": Field("float", 750.0, "Upper wavelength bound, nm (SYN-006).", min=0.0),
        "sample_interval": Field("float", 0.5, "Wavelength sampling interval, nm (SYN-006).", min=1e-6),
        "fwhm": Field("float", 2.0, "Default line FWHM, nm (SYN-004).", min=1e-6),
        "snr": Field("float", 100.0, "Signal-to-noise ratio (SYN-005).", min=0.0),
        "baseline": Field("float", 0.0, "Baseline level (SYN-006)."),
        "baseline_slope": Field("float", 0.0, "Baseline slope per nm (SYN-006)."),
        "profile_type": Field(
            "str", "gaussian",
            "Line profile (SYN-007). Only 'gaussian' is implemented initially.",
            choices=["gaussian", "lorentzian", "voigt"],
        ),
        "seed": Field("int", 0, "Deterministic RNG seed for reproducibility (SYN-006, SYN-009).", min=0),
    },
}
