"""Synthetic spectrum generation (SYN-001..SYN-009).

Produces reproducible, multi-line test spectra that flow through the same
analysis pipeline as acquired spectra (SYN-008). Gaussian profiles first;
Lorentzian and Voigt are declared as future extensions (SYN-007).
"""

from .generator import SyntheticSpectrumSpec, generate

__all__ = ["SyntheticSpectrumSpec", "generate"]
