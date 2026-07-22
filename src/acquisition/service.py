"""Acquisition service (Architecture §3; Migration Plan Phase 5).

Drives a camera adapter to capture a frame and hands it to spectrum extraction,
attaching acquisition metadata. Depends only on the camera contract, so it works
identically with USB, Raspberry Pi, or synthetic cameras.
"""

from __future__ import annotations

from typing import Optional

from cameras.base import CameraAdapter
from processing.extraction import extract_spectrum
from processing.spectrum import Spectrum


def acquire_spectrum(camera: CameraAdapter, center_row: Optional[int] = None,
                     average_rows: int = 3) -> Spectrum:
    """Capture one frame from ``camera`` and extract a :class:`Spectrum`."""
    frame, meta = camera.acquire_frame()
    spectrum = extract_spectrum(
        frame, center_row=center_row, average_rows=average_rows,
        source=meta.extra.get("source", "camera"),
    )
    spectrum.metadata["frame"] = {
        "width": meta.width, "height": meta.height,
        "pixel_format": meta.pixel_format, **meta.extra,
    }
    return spectrum
