"""Camera adapter factory (Migration Plan Phase 5).

Selects an adapter by backend name so callers depend on the contract, not a
specific camera API. Backends: ``usb``, ``picamera2``, ``synthetic``, ``auto``.
"""

from __future__ import annotations

from typing import Any, Mapping

from errors import CameraError
from .base import CameraAdapter
from .synthetic_camera import SyntheticCameraAdapter
from .usb import UsbCameraAdapter
from .picamera2 import Picamera2Adapter


def create_camera(backend: str = "usb", **kwargs: Any) -> CameraAdapter:
    backend = (backend or "usb").lower()
    if backend == "synthetic":
        return SyntheticCameraAdapter(**kwargs)
    if backend == "usb":
        return UsbCameraAdapter(**kwargs)
    if backend == "picamera2":
        return Picamera2Adapter(**kwargs)
    if backend == "auto":
        return _auto(**kwargs)
    raise CameraError(f"unknown camera backend: {backend!r}")


def create_camera_from_config(camera_cfg: Mapping[str, Any], **overrides: Any) -> CameraAdapter:
    """Build an adapter from a config ``[camera]`` section."""
    backend = str(camera_cfg.get("backend", "usb")).lower()
    kwargs: dict[str, Any] = {
        "width": camera_cfg.get("width", 800),
        "height": camera_cfg.get("height", 600),
    }
    if backend in ("usb", "auto"):
        kwargs["device_index"] = camera_cfg.get("device_index", 0)
    kwargs.update(overrides)
    return create_camera(backend, **kwargs)


def _auto(**kwargs: Any) -> CameraAdapter:
    """Prefer the Pi camera when ``picamera2`` is importable, else USB."""
    try:
        import picamera2  # noqa: F401
        return Picamera2Adapter(**{k: v for k, v in kwargs.items() if k in ("width", "height", "fps", "gain")})
    except ImportError:
        return UsbCameraAdapter(**{k: v for k, v in kwargs.items()
                                   if k in ("device_index", "width", "height", "fps", "api_preference")})
