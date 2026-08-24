"""Synthetic (hardware-free) camera adapter (Migration Plan Phase 5).

Produces frames whose columns encode a pixel-space synthetic spectrum, so the
entire acquisition -> extraction -> analysis path can run and be tested without
any hardware. Conforms to the common camera contract (Architecture §5).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from errors import CameraError
from .base import CameraAdapter, FrameMetadata

_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))

# Default emission lines in PIXEL space: (center_px, amplitude, fwhm_px).
DEFAULT_LINES = [(120, 200.0, 8.0), (300, 120.0, 6.0), (410, 180.0, 10.0), (610, 90.0, 7.0)]


class SyntheticCameraAdapter(CameraAdapter):
    """A camera that fabricates deterministic spectral frames."""

    def __init__(self, width: int = 800, height: int = 600,
                 lines: Optional[Sequence] = None, baseline: float = 5.0,
                 noise: float = 0.0, seed: int = 0, pixel_format: str = "GRAY"):
        self.width = int(width)
        self.height = int(height)
        self.lines = list(lines) if lines is not None else list(DEFAULT_LINES)
        self.baseline = float(baseline)
        self.noise = float(noise)
        self.seed = int(seed)
        self.pixel_format = pixel_format
        self._open = False
        self._frames = 0

    def initialize(self) -> None:
        self._open = True
        self._frames = 0

    def discover_capabilities(self) -> dict[str, Any]:
        return {
            "backend": "synthetic",
            "widths": [self.width],
            "heights": [self.height],
            "formats": ["GRAY", "BGR"],
            "lines": len(self.lines),
        }

    def configure(self, **settings: Any) -> None:
        for key in ("width", "height", "baseline", "noise", "seed", "pixel_format", "lines"):
            if key in settings:
                setattr(self, key, settings[key])
        self.width = int(self.width)
        self.height = int(self.height)

    def _column_profile(self) -> np.ndarray:
        x = np.arange(self.width, dtype=float)
        y = np.full(self.width, self.baseline, dtype=float)
        for center, amp, fwhm in self.lines:
            sigma = fwhm * _FWHM_TO_SIGMA
            y = y + amp * np.exp(-0.5 * ((x - center) / sigma) ** 2)
        return np.clip(y, 0, 255)

    def acquire_frame(self) -> tuple[Any, FrameMetadata]:
        if not self._open:
            raise CameraError("camera not initialized")
        profile = self._column_profile()
        if self.noise > 0:
            rng = np.random.default_rng(self.seed + self._frames)
            profile = np.clip(profile + rng.normal(0.0, self.noise, size=self.width), 0, 255)
        gray = np.tile(profile.astype(np.uint8), (self.height, 1))
        frame = np.repeat(gray[:, :, None], 3, axis=2) if self.pixel_format == "BGR" else gray
        meta = FrameMetadata(
            width=self.width, height=self.height, pixel_format=self.pixel_format,
            # 'synthetic-camera' is a simulated *frame* pushed through the real
            # pixel-extraction path — distinct from 'synthetic-generator', which
            # synthesizes a calibrated spectrum directly. A calibration fitted
            # on one is not valid for the other.
            extra={"source": "synthetic", "backend": "synthetic-camera",
                   "frame_index": self._frames, "lines": list(self.lines)},
        )
        self._frames += 1
        return frame, meta

    def status(self) -> dict[str, Any]:
        return {"backend": "synthetic", "open": self._open, "frames_acquired": self._frames}

    def shutdown(self) -> None:
        self._open = False
