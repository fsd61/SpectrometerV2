"""Reference data: emission line lists from the NIST Atomic Spectra Database.

Read-only at run time; refreshed with ``scripts/fetch_nist_lines.py``.
"""

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
    "DATA_DIR", "ReferenceLine", "available_species", "by_strength", "load_lines",
    "nearest", "read_header", "strength_label",
]
