"""Reference data: emission line lists from the NIST Atomic Spectra Database.

Read-only at run time; refreshed with ``scripts/fetch_nist_lines.py``.
"""

from .identify import Candidate, identify, refine_peak, wavelength_at
from .lines import (
    DATA_DIR,
    ReferenceLine,
    available_species,
    by_strength,
    load_lines,
    nearest,
    read_header,
    strength_label,
)

__all__ = [
    "DATA_DIR", "Candidate", "ReferenceLine", "available_species", "by_strength",
    "identify", "load_lines", "nearest", "read_header", "refine_peak",
    "strength_label", "wavelength_at",
]
