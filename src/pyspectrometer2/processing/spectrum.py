"""The shared 1-D spectrum data object.

Both the acquisition/extraction path and the synthetic generator produce a
``Spectrum``; the analysis pipeline consumes it. Keeping one type is what lets
synthetic and real data share a single code path (Architecture §6; SYN-008).
The ``metadata`` mapping carries provenance for reproducibility (SYN-009,
DATA-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class Spectrum:
    """A one-dimensional spectrum: intensity as a function of wavelength.

    Attributes:
        wavelengths: Monotonic wavelength axis (nm). May be empty if the
            spectrum is not yet wavelength-calibrated (pixel axis lives in
            ``metadata`` in that case).
        intensities: Intensity values, one per wavelength/pixel sample.
        metadata: Free-form provenance: source, config snapshot, calibration
            id, synthetic-generation parameters, timestamps, etc.
    """

    wavelengths: Sequence[float]
    intensities: Sequence[float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.wavelengths) not in (0, len(self.intensities)):
            raise ValueError(
                "wavelengths and intensities must be the same length "
                f"(got {len(self.wavelengths)} and {len(self.intensities)})"
            )

    def __len__(self) -> int:
        return len(self.intensities)
