"""Acquisition service (Architecture §3; Migration Plan Phase 5).

Drives a camera adapter to capture a frame and hands it to spectrum extraction,
attaching acquisition metadata. Depends only on the camera contract, so it works
identically with USB, Raspberry Pi, or synthetic cameras.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from cameras.base import CameraAdapter
from processing.extraction import extract_spectrum
from processing.spectrum import Spectrum


def extraction_settings(processing: Mapping[str, Any]) -> dict[str, Any]:
    """Map the ``[processing]`` config section onto extraction keyword arguments.

    The single place that interprets ``slice_row`` / ``slice_height`` /
    ``slice_precision``, so the GUI and the CLI can never extract differently
    from the same configuration. Missing keys fall back to the baseline
    (frame center, 3 rows, integer).
    """
    slice_row = processing.get("slice_row", -1)
    return {
        "center_row": None if slice_row is None or int(slice_row) < 0 else int(slice_row),
        "average_rows": int(processing.get("slice_height", 3)),
        "precision": str(processing.get("slice_precision", "integer")),
    }


def acquire_spectrum(camera: CameraAdapter, center_row: Optional[int] = None,
                     average_rows: int = 3, precision: str = "integer") -> Spectrum:
    """Capture one frame from ``camera`` and extract a :class:`Spectrum`."""
    frame, meta = camera.acquire_frame()
    spectrum = extract_spectrum(
        frame, center_row=center_row, average_rows=average_rows,
        source=meta.extra.get("source", "camera"), precision=precision,
    )
    spectrum.metadata["frame"] = {
        "width": meta.width, "height": meta.height,
        "pixel_format": meta.pixel_format, **meta.extra,
    }
    return spectrum
