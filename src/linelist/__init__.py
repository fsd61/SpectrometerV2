"""Atomic line lists: pinned reference wavelengths and their provenance.

This package is the *provider* half of the NIST work. It knows how to read a
pinned ASD export, which medium the wavelengths are quoted in, and how to derive
defensible relative intensities — and nothing about spectra, detectors, or
calibration fitting.

That separation is deliberate. Two very different consumers need this data:

* :mod:`synthetic` builds test spectra from it (a test fixture),
* :mod:`calibration` uses it as the reference atlas for an arc-lamp solution
  (the production path).

Keeping the provider free of both means the production calibration path never
imports the synthetic generator, so a synthetic spectrum can never be mistaken
for instrument validation.
"""

from .airvacuum import air_to_vacuum, refractive_index, vacuum_to_air
from .asd import load_line_list, parse_asd_lines
from .intensity import (
    DEFAULT_TEMPERATURE_EV,
    boltzmann_intensities,
    boltzmann_intensity,
    kelvin_to_ev,
    usable_lines,
)
from .records import LineList, Provenance, SpectralLine, WavelengthConvention

__all__ = [
    "air_to_vacuum",
    "vacuum_to_air",
    "refractive_index",
    "load_line_list",
    "parse_asd_lines",
    "LineList",
    "SpectralLine",
    "Provenance",
    "WavelengthConvention",
    "boltzmann_intensity",
    "boltzmann_intensities",
    "usable_lines",
    "kelvin_to_ev",
    "DEFAULT_TEMPERATURE_EV",
]
