"""Acquisition service: frame capture and acquisition metadata.

Drives a CameraAdapter to capture frames and hands normalized frames to spectrum
extraction; depends only on the camera contract (Architecture §3).
"""

from .service import acquire_spectrum

__all__ = ["acquire_spectrum"]
