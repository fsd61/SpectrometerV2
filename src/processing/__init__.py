"""Spectrum extraction and preprocessing.

Converts normalized camera frames into 1-D spectra and defines the shared
``Spectrum`` data object consumed by both acquired-data and synthetic paths so
synthetic spectra flow through the same analysis pipeline (SYN-008).
"""

from .spectrum import Spectrum
from .extraction import extract_intensity, extract_spectrum, to_grayscale

__all__ = ["Spectrum", "extract_intensity", "extract_spectrum", "to_grayscale"]
