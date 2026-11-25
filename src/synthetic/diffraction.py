"""Synthetic single-slit diffraction for the slit-width calibration (SYN-010).

Simulates what the user sees on the wall when a laser goes through the
entrance slit: noisy pencil-mark positions of the dark fringes, and the full
intensity profile along the wall. Lets the slit-width fit be exercised and
tested with no laser, slit or wall.

The geometry here is written from the angle (theta = asin(m*lambda/a),
y = L*tan(theta)) and the intensity from the Fraunhofer amplitude, on purpose
independently of :mod:`calibration.slit`, so tests compare two derivations
rather than one function with itself.

Reproducible: identical spec and seed give identical output (NumPy PCG64).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np

GENERATOR_ID = "single-slit-v1"


@dataclass
class DiffractionSpec:
    """One laser-through-slit setup. Units: um, nm, mm."""

    width_um: float = 12.7                  # 0.0005" fixed slit
    wavelength_nm: float = 650.0
    distance_mm: float = 2000.0             # slit to wall, perpendicular
    orders: Sequence[int] = (-4, -3, -2, -1, 1, 2, 3, 4)
    center_mm: float = 500.0                # pattern center as read on the tape
    direction: int = 1                      # +1: tape grows toward +orders
    mark_sigma_mm: float = 1.0              # pencil-mark scatter
    seed: int = 0


def simulate_marks(spec: DiffractionSpec) -> tuple[list[int], list[float]]:
    """Return (orders, tape positions in mm) of the marked dark fringes."""
    if spec.direction not in (1, -1):
        raise ValueError("direction must be +1 or -1")
    rng = np.random.default_rng(spec.seed)
    orders, positions = [], []
    for m in spec.orders:
        if m == 0:
            raise ValueError("order 0 is the bright center, not a dark fringe")
        s = m * spec.wavelength_nm * 1e-3 / spec.width_um     # sin(theta)
        if abs(s) >= 1.0:
            raise ValueError(f"order {m} does not exist for this slit and wavelength")
        theta = math.asin(s)
        y = spec.center_mm + spec.direction * spec.distance_mm * math.tan(theta)
        if spec.mark_sigma_mm > 0:
            y += float(rng.normal(0.0, spec.mark_sigma_mm))
        orders.append(int(m))
        positions.append(y)
    return orders, positions


def wall_profile(spec: DiffractionSpec, positions_mm: Sequence[float], *,
                 peak: float = 1.0, background: float = 0.0,
                 noise_sigma: float = 0.0) -> np.ndarray:
    """Intensity along the wall: Fraunhofer sinc^2 in the exact angle.

    I = peak * sinc^2(a sin(theta) / lambda), sin(theta) = x / sqrt(x^2 + L^2).
    The slow cos/distance falloff across the wall is ignored; it moves the
    bright maxima very slightly but never the zeros, which are what get marked.
    """
    x = spec.direction * (np.asarray(positions_mm, dtype=float) - spec.center_mm)
    sin_theta = x / np.hypot(x, spec.distance_mm)
    arg = spec.width_um * 1e3 * sin_theta / spec.wavelength_nm   # a sin(theta)/lambda
    intensity = peak * np.sinc(arg) ** 2 + background            # np.sinc = sin(pi t)/(pi t)
    if noise_sigma > 0:
        rng = np.random.default_rng(spec.seed)
        intensity = intensity + rng.normal(0.0, noise_sigma, size=intensity.shape)
    return intensity


def simulate_dial_series(scale_um_per_unit: float, zero_dial: float,
                         dial_readings: Sequence[float], base: DiffractionSpec,
                         ) -> list[tuple[float, list[int], list[float]]]:
    """A variable-slit calibration session: one set of marks per dial setting.

    True width at each setting is scale * (dial - zero). Orders that do not
    exist at a narrow setting are dropped. Each setting gets its own seed.
    Returns [(dial, orders, positions_mm), ...].
    """
    out = []
    for i, dial in enumerate(dial_readings):
        width = scale_um_per_unit * (dial - zero_dial)
        if width <= 0:
            raise ValueError(f"dial {dial} is at or below the mechanical zero")
        lam_um = base.wavelength_nm * 1e-3
        orders = [m for m in base.orders if abs(m) * lam_um < 0.95 * width]
        spec = replace(base, width_um=width, orders=tuple(orders), seed=base.seed + i)
        o, p = simulate_marks(spec)
        out.append((float(dial), o, p))
    return out
