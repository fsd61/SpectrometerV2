"""Spectrum extraction and preprocessing.

Converts normalized camera frames into 1-D spectra. Also defines the shared
``Spectrum`` data object consumed by both acquired-data and synthetic paths so
that synthetic spectra flow through the *same* analysis pipeline (SYN-008).
"""

from .spectrum import Spectrum

__all__ = ["Spectrum"]
