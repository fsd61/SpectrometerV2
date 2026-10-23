"""Spectrum extraction (Migration Plan Phase 3 extraction).

Ports the baseline's sensor-frame -> 1-D intensity step from the main capture
loop of ``PySpectrometer2-USB-v1.0.py`` into a platform-neutral function.

Baseline behavior (preserved):
  * The averaged band is centered on the frame's vertical middle. In the
    baseline the crop origin is ``int(H/2) - 40`` and the sampled row is the
    crop's half-height (``+40``); those cancel, so the center row is ``H // 2``.
  * Three rows (center-1, center, center+1) are averaged per column.
  * The mean is cast to ``uint8`` (truncation), matching ``np.uint8(data)``.

Color conversion (``to_grayscale``) approximates OpenCV's BGR2GRAY luminance
weights; exact camera/color handling belongs to the camera adapter layer
(Phase 5). The 3-row averaging itself is exact.

Extension beyond the baseline (opt-in; defaults reproduce it exactly):
  * ``average_rows`` may be any odd height, so the band can cover more of the
    slit image. Averaging N rows of independent noise improves SNR by ~sqrt(N);
    it cannot improve resolution, and a tilted slit image broadens lines as the
    band grows.
  * ``precision="float"`` keeps the fractional mean instead of truncating to
    uint8. With a tall band the noise falls below one count, so truncation
    would otherwise throw most of the gain away.
"""

from __future__ import annotations

import numpy as np

from .spectrum import Spectrum

# Standard luminance weights (OpenCV BGR2GRAY): 0.114 B + 0.587 G + 0.299 R.
_BGR_WEIGHTS = (0.114, 0.587, 0.299)


def to_grayscale(frame):
    """Return a 2-D grayscale view of ``frame``.

    Accepts a 2-D array (returned unchanged) or a 3-D BGR array (OpenCV
    convention), converted via standard luminance weights.
    """
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 3:
        b, g, r = (frame[..., i].astype(float) for i in range(3))
        wb, wg, wr = _BGR_WEIGHTS
        return wb * b + wg * g + wr * r
    raise ValueError("frame must be a 2-D grayscale or 3-D BGR image")


PRECISIONS = ("integer", "float")


def extract_intensity(gray, center_row=None, average_rows=3, precision="integer"):
    """Average ``average_rows`` rows about ``center_row`` into a 1-D intensity.

    Args:
        gray: 2-D grayscale array (H, W).
        center_row: row to center on; ``None`` or negative -> ``H // 2``
            (baseline default).
        average_rows: positive odd row count to average (baseline: 3).
        precision: ``"integer"`` (baseline) truncates the mean to uint8;
            ``"float"`` returns the exact mean as float64.

    Returns:
        ``np.ndarray`` of length W: uint8 (truncated mean per column) for
        ``"integer"``, float64 for ``"float"``.
    """
    if precision not in PRECISIONS:
        raise ValueError(f"precision must be one of {PRECISIONS}, got {precision!r}")
    gray = np.asarray(gray)
    if gray.ndim != 2:
        raise ValueError("gray must be a 2-D array")
    height, _ = gray.shape
    if center_row is None or center_row < 0:
        center_row = height // 2
    if average_rows < 1 or average_rows % 2 != 1:
        raise ValueError("average_rows must be a positive odd integer")
    half = average_rows // 2
    if center_row - half < 0 or center_row + half >= height:
        raise ValueError("averaging window falls outside the frame")
    band = gray[center_row - half : center_row + half + 1, :].astype(np.int64)
    mean = band.sum(axis=0) / float(average_rows)
    if precision == "float":
        return mean
    return mean.astype(np.uint8)  # truncation matches baseline np.uint8(data)


def extract_spectrum(frame, center_row=None, average_rows=3, source="camera",
                     precision="integer"):
    """Extract a :class:`Spectrum` (pixel axis; uncalibrated) from a frame."""
    gray = to_grayscale(frame)
    intensity = extract_intensity(gray, center_row=center_row, average_rows=average_rows,
                                  precision=precision)
    height, width = gray.shape
    center = height // 2 if (center_row is None or center_row < 0) else center_row
    as_number = float if precision == "float" else int
    return Spectrum(
        wavelengths=[],
        intensities=[as_number(v) for v in intensity],
        metadata={
            "source": source,
            "width": int(width),
            "height": int(height),
            "center_row": int(center),
            "average_rows": int(average_rows),
            "precision": precision,
            "extraction": f"{average_rows}-row-mean"
                          + ("" if precision == "integer" else "-float"),
        },
    )
