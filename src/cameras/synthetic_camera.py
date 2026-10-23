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
                 noise: float = 0.0, seed: int = 0, pixel_format: str = "GRAY",
                 pixel_noise: float = 0.0, slit_rows: Optional[int] = None,
                 tilt: float = 0.0):
        """Create a synthetic camera.

        ``noise`` is the original per-*column* noise: one random value per
        column, identical down every row, so averaging rows cannot reduce it.
        The remaining options model a real sensor and default to off, which
        keeps the original frames exactly:

        * ``pixel_noise``: independent Gaussian noise (std, counts) on every
          pixel, as from shot and read noise. This is what row averaging reduces.
        * ``slit_rows``: height of the illuminated slit image, centered on the
          frame; rows outside it see only the dark ``baseline``.
        * ``tilt``: line shift in pixels per row away from the center row,
          modelling a slit image that is not perfectly perpendicular to the
          dispersion. Averaging a tall band of a tilted image broadens lines.
        """
        self.width = int(width)
        self.height = int(height)
        self.lines = list(lines) if lines is not None else list(DEFAULT_LINES)
        self.baseline = float(baseline)
        self.noise = float(noise)
        self.seed = int(seed)
        self.pixel_format = pixel_format
        self.pixel_noise = float(pixel_noise)
        self.slit_rows = None if slit_rows is None else int(slit_rows)
        self.tilt = float(tilt)
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
        for key in ("width", "height", "baseline", "noise", "seed", "pixel_format", "lines",
                    "pixel_noise", "slit_rows", "tilt"):
            if key in settings:
                setattr(self, key, settings[key])
        self.width = int(self.width)
        self.height = int(self.height)

    @property
    def _realistic(self) -> bool:
        """True when any sensor-realism option is on (otherwise: original frames)."""
        return self.pixel_noise > 0 or self.slit_rows is not None or self.tilt != 0

    def _render_frame(self, column_noise: np.ndarray, rng) -> np.ndarray:
        """Render a 2-D frame with slit height, tilt and per-pixel noise."""
        rows = np.arange(self.height, dtype=float)[:, None]
        cols = np.arange(self.width, dtype=float)[None, :]
        center = self.height // 2
        signal = np.zeros((self.height, self.width))
        for line_center, amp, fwhm in self.lines:
            sigma = fwhm * _FWHM_TO_SIGMA
            shifted = line_center + self.tilt * (rows - center)
            signal += amp * np.exp(-0.5 * ((cols - shifted) / sigma) ** 2)
        if self.slit_rows is not None:
            top = center - self.slit_rows // 2
            lit = (rows >= top) & (rows < top + self.slit_rows)
            signal = np.where(lit, signal, 0.0)
        frame = self.baseline + signal + column_noise[None, :]
        if self.pixel_noise > 0:
            frame = frame + rng.normal(0.0, self.pixel_noise, size=frame.shape)
        # Rounded like a sensor's ADC (the original path truncates a single row).
        return np.clip(np.rint(frame), 0, 255).astype(np.uint8)

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
        rng = np.random.default_rng(self.seed + self._frames)
        if self._realistic:
            column_noise = (rng.normal(0.0, self.noise, size=self.width)
                            if self.noise > 0 else np.zeros(self.width))
            gray = self._render_frame(column_noise, rng)
        else:
            profile = self._column_profile()
            if self.noise > 0:
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
