"""Helpers for baseline characterization / golden regression tests.

Loads Les Wright's original ``specFunctions.py`` (preserved under
``Original_Pyspectrometer2/``, tag ``baseline-v1.0``) and provides a
deterministic synthetic-spectrum generator for reproducible fixtures.

Purpose (Migration Plan Phase 1): PIN the proven baseline scientific behavior so
the migrated core can later be proven numerically equivalent. Golden fixtures
store the *outputs*; deterministic inputs are regenerated here (NumPy's PCG64
``default_rng`` stream is stable across versions), so only expected results are
committed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SPECFUNCTIONS = (
    REPO_ROOT / "Original_Pyspectrometer2" / "src" / "specFunctions.py"
)
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def load_baseline():
    """Import the baseline specFunctions module from the preserved source."""
    spec = importlib.util.spec_from_file_location(
        "baseline_specFunctions", BASELINE_SPECFUNCTIONS
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gaussian(x, center, amplitude, fwhm):
    """A Gaussian line: amplitude at center, given full-width-half-maximum."""
    sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def synthetic_spectrum(width=800, lines=None, baseline=5.0, noise=0.0, seed=0):
    """Deterministic multi-Gaussian spectrum on a pixel axis [0, width).

    Args:
        width: number of samples (pixels).
        lines: iterable of (center_px, amplitude, fwhm_px).
        baseline: constant offset.
        noise: stddev of additive Gaussian noise (0 = noiseless).
        seed: RNG seed for the noise (PCG64 stream is version-stable).

    Returns:
        (x, y) as float64 ndarrays.
    """
    x = np.arange(width, dtype=np.float64)
    y = np.full(width, float(baseline), dtype=np.float64)
    for c, a, f in (lines or []):
        y += gaussian(x, c, a, f)
    if noise > 0:
        rng = np.random.default_rng(seed)
        y = y + rng.normal(0.0, noise, size=width)
    return x, y


# ---- Shared, fixed reference fixtures (do not change without regenerating golden) ----

# Four well-separated emission lines (center_px, amplitude, fwhm_px).
REFERENCE_LINES = [
    (120, 200.0, 8.0),
    (300, 120.0, 6.0),
    (410, 180.0, 10.0),
    (610, 90.0, 7.0),
]
REFERENCE_WIDTH = 800
REFERENCE_BASELINE = 5.0
REFERENCE_NOISE = 1.5
REFERENCE_SEED = 20260716

# Multi-point wavelength calibration (pixels -> nm), monotonic increasing.
# Loosely models mercury/argon lamp lines across the sensor.
CAL_PIXELS = [35, 250, 470, 700]
CAL_WAVELENGTHS = [404.66, 435.83, 546.07, 611.60]
# A minimal 3-point calibration to exercise the 2nd-order branch.
CAL3_PIXELS = [0, 400, 800]
CAL3_WAVELENGTHS = [380.0, 560.0, 750.0]


def reference_spectrum():
    """The canonical noisy reference spectrum used by characterization tests."""
    return synthetic_spectrum(
        width=REFERENCE_WIDTH,
        lines=REFERENCE_LINES,
        baseline=REFERENCE_BASELINE,
        noise=REFERENCE_NOISE,
        seed=REFERENCE_SEED,
    )


def write_caldata(directory: Path, pixels, wavelengths):
    """Write a caldata.txt (baseline format) into *directory*; return its path."""
    directory = Path(directory)
    path = directory / "caldata.txt"
    path.write_text(
        ",".join(str(p) for p in pixels) + "\r\n"
        + ",".join(str(w) for w in wavelengths) + "\r\n",
        encoding="utf-8", newline="",
    )
    return path
