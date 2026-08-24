"""Synthetic spectrum generator (Migration Plan Phase 4; SYN-001..SYN-009).

Produces reproducible, multi-line test spectra on a wavelength axis and returns
the shared :class:`Spectrum`, so synthetic data flows through the *same* analysis
pipeline as acquired data (SYN-008). Gaussian profiles are implemented; Lorentzian
and Voigt are declared extension points (SYN-007).

Reproducibility (SYN-006, SYN-009): identical inputs and seed yield identical
output (NumPy PCG64 ``default_rng``), and the complete generation parameters are
stored in ``Spectrum.metadata``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from processing.spectrum import Spectrum

GENERATOR_ID = "gaussian-v1"
_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
SUPPORTED_PROFILES = ("gaussian",)          # SYN-007: lorentzian/voigt are future


@dataclass
class SyntheticSpectrumSpec:
    """Full generation specification (mirrors the [synthetic] config section)."""

    center_wavelengths: Sequence[float]                     # SYN-002
    amplitudes: Sequence[float]                             # SYN-003
    fwhm: float = 2.0                                       # SYN-004 (global)
    per_line_fwhm: Sequence[float] = field(default_factory=tuple)  # SYN-004 (optional)
    wavelength_min: float = 380.0                           # SYN-006
    wavelength_max: float = 750.0                           # SYN-006
    sample_interval: float = 0.5                            # SYN-006
    snr: float = 100.0                                      # SYN-005
    baseline: float = 0.0                                   # SYN-006
    baseline_slope: float = 0.0                             # SYN-006 (per nm)
    profile_type: str = "gaussian"                          # SYN-007
    seed: int = 0                                           # SYN-006, SYN-009

    @classmethod
    def from_config(cls, synthetic_cfg, center_wavelengths, amplitudes, per_line_fwhm=()):
        """Build a spec from a config ``[synthetic]`` section plus the lines."""
        return cls(
            center_wavelengths=list(center_wavelengths),
            amplitudes=list(amplitudes),
            per_line_fwhm=list(per_line_fwhm),
            fwhm=synthetic_cfg["fwhm"],
            wavelength_min=synthetic_cfg["wavelength_min"],
            wavelength_max=synthetic_cfg["wavelength_max"],
            sample_interval=synthetic_cfg["sample_interval"],
            snr=synthetic_cfg["snr"],
            baseline=synthetic_cfg["baseline"],
            baseline_slope=synthetic_cfg["baseline_slope"],
            profile_type=synthetic_cfg["profile_type"],
            seed=synthetic_cfg["seed"],
        )


def _resolve_fwhms(spec: SyntheticSpectrumSpec) -> list[float]:
    n = len(spec.center_wavelengths)
    if spec.per_line_fwhm:
        if len(spec.per_line_fwhm) != n:
            raise ValueError("per_line_fwhm length must match center_wavelengths")
        return [float(f) for f in spec.per_line_fwhm]
    return [float(spec.fwhm)] * n


def _wavelength_axis(spec: SyntheticSpectrumSpec) -> np.ndarray:
    if spec.wavelength_max <= spec.wavelength_min:
        raise ValueError("wavelength_max must exceed wavelength_min")
    if spec.sample_interval <= 0:
        raise ValueError("sample_interval must be positive")
    n = int(round((spec.wavelength_max - spec.wavelength_min) / spec.sample_interval)) + 1
    return spec.wavelength_min + spec.sample_interval * np.arange(n, dtype=float)


def generate(spec: SyntheticSpectrumSpec) -> Spectrum:
    """Generate a reproducible synthetic :class:`Spectrum` from ``spec``."""
    if len(spec.center_wavelengths) != len(spec.amplitudes):
        raise ValueError("center_wavelengths and amplitudes must be the same length")
    if spec.profile_type not in SUPPORTED_PROFILES:
        raise NotImplementedError(
            f"profile_type {spec.profile_type!r} is not yet supported "
            f"(supported: {SUPPORTED_PROFILES}; Lorentzian/Voigt are future - SYN-007)"
        )
    fwhms = _resolve_fwhms(spec)
    if any(f <= 0 for f in fwhms):
        raise ValueError("FWHM values must be positive")

    wl = _wavelength_axis(spec)
    y = spec.baseline + spec.baseline_slope * (wl - spec.wavelength_min)
    for center, amp, fwhm in zip(spec.center_wavelengths, spec.amplitudes, fwhms):
        sigma = fwhm * _FWHM_TO_SIGMA
        y = y + amp * np.exp(-0.5 * ((wl - center) / sigma) ** 2)

    # SYN-005: SNR relative to the strongest line; seed makes it reproducible.
    noise_sigma = 0.0
    if spec.snr and spec.snr > 0 and len(spec.amplitudes):
        reference = float(max(spec.amplitudes))
        noise_sigma = reference / float(spec.snr)
        if noise_sigma > 0:
            rng = np.random.default_rng(spec.seed)
            y = y + rng.normal(0.0, noise_sigma, size=len(wl))

    metadata = {
        "source": "synthetic",
        "backend": "synthetic-generator",
        "generator": GENERATOR_ID,
        "profile_type": spec.profile_type,
        "center_wavelengths": list(map(float, spec.center_wavelengths)),
        "amplitudes": list(map(float, spec.amplitudes)),
        "fwhm": list(map(float, fwhms)),
        "wavelength_min": float(spec.wavelength_min),
        "wavelength_max": float(spec.wavelength_max),
        "sample_interval": float(spec.sample_interval),
        "snr": float(spec.snr),
        "noise_sigma": float(noise_sigma),
        "baseline": float(spec.baseline),
        "baseline_slope": float(spec.baseline_slope),
        "seed": int(spec.seed),
        "n_samples": int(len(wl)),
    }
    return Spectrum(
        wavelengths=[float(v) for v in wl],
        intensities=[float(v) for v in y],
        metadata=metadata,
    )
