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
            "Camera source. 'auto' picks the CSI (Pi ribbon) camera on a "
            "Raspberry Pi, otherwise a USB camera; 'csi' = Pi ribbon camera; "
            "'usb' = USB/webcam; 'synthetic' = simulated data (clearly labelled). "
            "('picamera2' is accepted as an alias for 'csi'.)",
            choices=["auto", "usb", "csi", "picamera2", "synthetic"],
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
    "gui": {
        "fps": Field(
            "float", 15.0,
            "Target refresh rate for the live GUI view, frames per second.",
            min=0.1, max=120.0,
        ),
        "waterfall_frames": Field(
            "int", 256,
            "Number of recent frames (time rows) kept in the live waterfall.",
            min=10, max=4000,
        ),
        "snapshot_dir": Field(
            "path", "snapshots",
            "Directory where the GUI snapshot key (s) writes CSV + metadata.",
        ),
    },
    # Advanced-analysis GUI defaults (wavelet decomposition, simulated-annealing
    # line fitting). Kept flat (not 'analysis.wavelet') so '--set wavelet.key=...'
    # overrides work — the override parser splits section/key on the first dot.
    "wavelet": {
        "wavelet": Field(
            "str", "db4",
            "PyWavelets wavelet family for the decomposition view.",
            choices=["db4", "db6", "sym5", "coif3"],
        ),
        "level": Field(
            "int", 4,
            "Decomposition depth. Clamped at compute time to the maximum the "
            "sample count allows (see the effective-level readout).",
            min=1, max=12,
        ),
    },
    "annealing": {
        "schedule": Field(
            "str", "medium",
            "Cooling schedule: 'fast' (log), 'medium' (geometric), 'slow' (linear).",
            choices=["fast", "medium", "slow"],
        ),
        "max_cycles": Field(
            "int", 200, "Maximum temperature cycles (compute budget).",
            min=1, max=5000,
        ),
        "tol": Field(
            "float", 1e-5, "Normalized-error tolerance for early termination.",
            min=0.0, max=1.0,
        ),
        "n_components": Field(
            "int", 0,
            "Number of Gaussian components to fit; 0 = auto (derive from the "
            "detected peaks). Sets the Markov-chain length.",
            min=0, max=64,
        ),
        "bound_tightness": Field(
            "float", 0.5,
            "How tightly per-parameter bounds hug the seed values (0 = loose, "
            "1 = pinned). Used when bounds are derived from detected peaks.",
            min=0.0, max=1.0,
        ),
        "seed": Field(
            "int", 0, "Random seed; recorded with each fit for reproducibility.",
            min=0,
        ),
        "lock_seed": Field(
            "bool", True,
            "Reuse the fixed seed every run (reproducible). If false, each fit "
            "draws a fresh seed.",
        ),
    },
    # Optional InfluxDB telemetry sink (off by default). Writes scalar features
    # per acquisition as line protocol; the InfluxDB *server* is installed and run
    # separately — this only needs stdlib HTTP, no client library.
    "influx": {
        "enabled": Field("bool", False, "Also write each spectrum's scalar features to InfluxDB."),
        "version": Field(
            "int", 2,
            "InfluxDB major version of the target server (v3 uses the v2 write API).",
            choices=[1, 2, 3],
        ),
        "url": Field("str", "http://localhost:8086",
                     "Base URL of the InfluxDB server (local or remote)."),
        "org": Field("str", "", "Organization (v2/v3)."),
        "bucket": Field("str", "spectrometer", "Bucket to write to (v2/v3; on v3 this is the database name)."),
        "token": Field("str", "", "API token, sent as an Authorization header (v2/v3)."),
        "database": Field("str", "spectrometer", "Database name (v1)."),
        "username": Field("str", "", "Username (v1, optional)."),
        "password": Field("str", "", "Password (v1, optional)."),
        "measurement": Field("str", "spectrum", "InfluxDB measurement name for the written points."),
        "precision": Field(
            "str", "ns", "Timestamp precision.", choices=["ns", "us", "ms", "s"],
        ),
        "timeout": Field("float", 5.0, "HTTP write timeout, seconds.", min=0.1, max=120.0),
        "dry_run": Field(
            "bool", False,
            "Build and log the line protocol but do not POST it — for testing "
            "without a live server.",
        ),
    },
    # Optional SQLite store (off by default). Unlike InfluxDB, this is the
    # queryable system of record: it holds the spectrum arrays, calibration
    # records and full provenance. The two stores are complementary, not
    # interchangeable — see data/sqlite.py.
    "sqlite": {
        "enabled": Field("bool", False, "Also persist each spectrum to a SQLite database."),
        "path": Field(
            "path", "data/spectrometer.db",
            "SQLite database file. Created (with its parent directory) on first use.",
        ),
        "store_metadata_json": Field(
            "bool", True,
            "Archive the full metadata dict as JSON on each capture row. Costs "
            "space; keeps provenance that the typed columns do not cover.",
        ),
        "timeout": Field("float", 5.0, "Lock-wait timeout, seconds.", min=0.1, max=120.0),
        "journal_mode": Field(
            "str", "wal",
            "SQLite journal mode. 'wal' lets a dashboard or notebook read while "
            "acquisition writes.",
            choices=["wal", "delete", "truncate", "persist", "memory", "off"],
        ),
    },
    # User-declared extra fields. The core schema is locked; this is the only
    # sanctioned way to persist additional data, and one declaration applies to
    # both SQLite and InfluxDB. See data/user_schema.py for the file format.
    "user_schema": {
        "manifest": Field(
            "str", "",
            "Path to the user field manifest (INI). Blank = core schema only. "
            "Declared fields become typed SQLite columns and InfluxDB "
            "fields/tags. Kept out of this file because the config loader is "
            "closed-world, which is what keeps the core schema locked.",
        ),
        "hook": Field(
            "str", "",
            "Optional 'module:function' called per capture, returning a dict of "
            "user field values. Only needed for quantities the pipeline does not "
            "already produce; fields with a 'from' path need no code.",
        ),
        "on_violation": Field(
            "str", "error",
            "What to do when a user value fails validation (wrong type, outside "
            "'allowed', or undeclared): 'error' aborts the write, 'warn' logs and "
            "drops the value, 'drop' discards it silently.",
            choices=["error", "warn", "drop"],
        ),
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
