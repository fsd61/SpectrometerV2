"""Synthetic spectrum generator (Architecture §6; SYN-002..SYN-009). Phase 4 stub.

The dataclass captures the full parameter set required by the Requirements doc
so that downstream code and configuration can be wired now; the numerical
implementation lands in Migration Plan Phase 4, validated against preserved
behavior from the legacy generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from processing.spectrum import Spectrum


@dataclass
class SyntheticSpectrumSpec:
    """Full generation specification (mirrors the [synthetic] config section)."""

    center_wavelengths: Sequence[float]          # SYN-002 (multiple lines)
    amplitudes: Sequence[float]                  # SYN-003
    fwhm: float = 2.0                            # SYN-004 (global; per-line later)
    per_line_fwhm: Sequence[float] = field(default_factory=tuple)  # SYN-004 (optional)
    wavelength_min: float = 380.0               # SYN-006
    wavelength_max: float = 750.0               # SYN-006
    sample_interval: float = 0.5                # SYN-006
    snr: float = 100.0                          # SYN-005
    baseline: float = 0.0                       # SYN-006
    baseline_slope: float = 0.0                 # SYN-006
    profile_type: str = "gaussian"              # SYN-007
    seed: int = 0                               # SYN-006, SYN-009


def generate(spec: SyntheticSpectrumSpec) -> Spectrum:
    """Generate a reproducible synthetic ``Spectrum`` from ``spec``.

    Implemented in Migration Plan Phase 4. Must:
      * support multiple lines, amplitudes, and (global/per-line) FWHM,
      * apply baseline level and slope, and SNR-based noise with a fixed seed,
      * embed the complete generation parameters in ``Spectrum.metadata`` (SYN-009),
      * return the shared ``Spectrum`` object (SYN-008).
    """
    raise NotImplementedError(
        "Synthetic generator numerics arrive in Migration Plan Phase 4."
    )
