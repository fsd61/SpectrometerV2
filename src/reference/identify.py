"""Line identification: which reference lines could a measured peak be?

Qt-free so the GUI's Identify mode and tests share it. A peak's wavelength is
read off the current calibration (sub-pixel, from a parabola through the peak's
top three samples), then compared with the NIST line lists of the chosen
elements. Candidates within the tolerance come back nearest first.

Nearest is not proof: at ~0.27 nm per pixel several lines can sit within a
pixel or two of a peak. The strength label and knowing what is in the lamp do
the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from errors import CalibrationError

from .lines import ReferenceLine, load_lines, strength_label


@dataclass(frozen=True)
class Candidate:
    """A reference line near a measured peak."""

    line: ReferenceLine
    delta_nm: float          # reference minus measured
    strength: str            # 'very strong' ... 'weak', or '' if ASD gives none

    @property
    def species(self) -> str:
        return self.line.species

    @property
    def wavelength_nm(self) -> float:
        return self.line.wavelength_nm


def refine_peak(intensities: Sequence[float], pixel: int) -> float:
    """Sub-pixel peak position: vertex of the parabola through pixel-1..pixel+1.

    Returns ``pixel`` unchanged at the array edges or when the three points do
    not form a maximum. The shift is clamped to half a pixel.
    """
    y = np.asarray(intensities, dtype=float)
    p = int(pixel)
    if p <= 0 or p >= len(y) - 1:
        return float(p)
    left, mid, right = y[p - 1], y[p], y[p + 1]
    curvature = left - 2.0 * mid + right
    if curvature >= 0:                      # not a local maximum
        return float(p)
    shift = 0.5 * (left - right) / curvature
    return float(p + max(-0.5, min(0.5, shift)))


def wavelength_at(wavelengths: Sequence[float], position_px: float) -> float:
    """Interpolate the calibrated axis at a fractional pixel position."""
    wl = np.asarray(wavelengths, dtype=float)
    return float(np.interp(position_px, np.arange(len(wl)), wl))


def identify(wavelength_nm: float, species: Iterable[str], tolerance_nm: float = 1.0,
             data_dir: Path | None = None) -> list[Candidate]:
    """Reference lines of ``species`` within ``tolerance_nm`` of ``wavelength_nm``,
    nearest first. Species without a line file are skipped."""
    found: list[Candidate] = []
    for name in species:
        try:
            lines = load_lines(name, data_dir=data_dir)
        except CalibrationError:
            continue
        for ln in lines:
            delta = ln.wavelength_nm - wavelength_nm
            if abs(delta) <= tolerance_nm:
                found.append(Candidate(ln, delta, strength_label(ln, lines)))
    found.sort(key=lambda c: (abs(c.delta_nm), c.species))
    return found
