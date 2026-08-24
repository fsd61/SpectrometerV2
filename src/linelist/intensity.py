"""Physically-grounded relative line intensities.

ASD's ``Rel. Int.`` column is a qualitative, source-dependent number: it records
what some original observer saw in whatever discharge they ran, often on an
arbitrary per-publication scale. Two lines whose ASD intensities differ by 10x
may be comparable in an argon glow discharge, and vice versa. Using that column
as a peak amplitude produces a spectrum that looks plausible and is wrong.

The defensible alternative is a Boltzmann population model over the transition
data ASD *does* supply quantitatively:

    I(lambda) ~ (A_ki * g_k / lambda) * exp(-E_k / kT)

with ``A_ki`` the Einstein coefficient, ``g_k`` the upper-level degeneracy, and
``E_k`` the upper-level energy. It assumes local thermodynamic equilibrium at a
single excitation temperature, which a low-pressure glow discharge does not
strictly satisfy — so these are *relative* intensities for building a
representative test spectrum, not a radiometric prediction. For the FS-2's argon
4p->4s NIR manifold an excitation temperature of roughly 0.5-1.5 eV puts the
relative line strengths in a sensible range.

This module is intentionally free of any instrument model: broadening,
efficiency and detector response belong downstream.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .records import LineList, SpectralLine

#: Boltzmann constant in eV/K, for callers that prefer kelvin.
BOLTZMANN_EV_PER_K = 8.617333262e-5

#: Excitation temperature (eV) that gives a reasonable Ar I NIR distribution.
DEFAULT_TEMPERATURE_EV = 1.0


def kelvin_to_ev(temperature_k: float) -> float:
    """Convert an excitation temperature in kelvin to eV."""
    if temperature_k <= 0:
        raise ValueError("temperature must be positive")
    return temperature_k * BOLTZMANN_EV_PER_K


def boltzmann_intensity(
    line: SpectralLine,
    temperature_ev: float = DEFAULT_TEMPERATURE_EV,
) -> Optional[float]:
    """Unnormalized relative intensity for one line, or ``None`` if unusable.

    ``None`` (rather than a fallback value) is returned when A_ki, g_k or E_k is
    missing, so a caller cannot silently mix modelled and invented amplitudes.
    """
    if temperature_ev <= 0:
        raise ValueError("temperature_ev must be positive")
    if not line.has_boltzmann_terms():
        return None
    import math

    return (
        line.aki_s
        * line.g_upper
        / line.wavelength_nm
        * math.exp(-line.e_upper_ev / temperature_ev)
    )


def boltzmann_intensities(
    lines: LineList | Sequence[SpectralLine],
    temperature_ev: float = DEFAULT_TEMPERATURE_EV,
    normalize: bool = True,
) -> list[Optional[float]]:
    """Relative intensities for every line, ``None`` where terms are missing.

    With ``normalize`` the strongest usable line becomes 1.0, which is the form
    the synthetic generator wants (it scales noise to the largest amplitude).
    """
    values = [boltzmann_intensity(line, temperature_ev) for line in lines]
    if not normalize:
        return values
    usable = [v for v in values if v is not None and v > 0]
    if not usable:
        return values
    peak = max(usable)
    return [None if v is None else v / peak for v in values]


def usable_lines(
    lines: LineList | Sequence[SpectralLine],
    temperature_ev: float = DEFAULT_TEMPERATURE_EV,
    minimum: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Return ``(wavelengths, amplitudes)`` for lines that can be modelled.

    Lines lacking transition data are dropped rather than defaulted, and the
    pairing is positional — this is the shape
    :class:`synthetic.generator.SyntheticSpectrumSpec` consumes.
    """
    intensities = boltzmann_intensities(lines, temperature_ev, normalize=True)
    wavelengths: list[float] = []
    amplitudes: list[float] = []
    for line, value in zip(lines, intensities):
        if value is None or value < minimum:
            continue
        wavelengths.append(line.wavelength_nm)
        amplitudes.append(value)
    return wavelengths, amplitudes
