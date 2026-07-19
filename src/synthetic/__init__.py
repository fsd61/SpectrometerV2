"""Synthetic spectrum generation (SYN-001..SYN-009).

Produces reproducible, multi-line test spectra that flow through the same
analysis pipeline as acquired spectra (SYN-008). Gaussian profiles first;
Lorentzian and Voigt are declared as future extensions (SYN-007). SyntheticStream
adds a time-varying (streaming) source for live/waterfall development.
"""

from .generator import SyntheticSpectrumSpec, generate
from .stream import SyntheticStream

__all__ = ["SyntheticSpectrumSpec", "generate", "SyntheticStream"]
