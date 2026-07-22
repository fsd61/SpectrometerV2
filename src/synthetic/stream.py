"""Streaming (time-varying) synthetic source (Migration Plan Phase 4 extension).

Turns the one-shot generator into an evolving scene: line centers drift, line
amplitudes fluctuate, and each frame carries fresh seeded noise. Deterministic
for a given base seed, so a stream is fully reproducible while still moving —
the substrate for developing live/waterfall visualization and streamed storage
without hardware.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterator

from processing.spectrum import Spectrum
from .generator import SyntheticSpectrumSpec, generate


@dataclass
class SyntheticStream:
    """A reproducible, time-varying stream of synthetic spectra."""

    base: SyntheticSpectrumSpec
    drift_nm: float = 1.0        # peak-center drift amplitude (nm)
    drift_period: float = 30.0   # frames per drift cycle
    amp_jitter: float = 0.1      # fractional amplitude fluctuation

    def spectrum(self, t: int) -> Spectrum:
        """Return the synthetic spectrum for frame index ``t``."""
        phase = 2.0 * math.pi * t / self.drift_period
        centers = [
            c + self.drift_nm * math.sin(phase + i)
            for i, c in enumerate(self.base.center_wavelengths)
        ]
        amps = [
            a * (1.0 + self.amp_jitter * math.sin(1.3 * phase + i))
            for i, a in enumerate(self.base.amplitudes)
        ]
        frame_spec = replace(
            self.base, center_wavelengths=centers, amplitudes=amps,
            seed=self.base.seed + t,
        )
        spectrum = generate(frame_spec)
        spectrum.metadata["frame_index"] = int(t)
        spectrum.metadata["stream"] = True
        return spectrum

    def iter_spectra(self, n: int) -> Iterator[Spectrum]:
        """Yield ``n`` consecutive frames (t = 0..n-1)."""
        for t in range(int(n)):
            yield self.spectrum(t)
