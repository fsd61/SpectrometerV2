"""Raspberry Pi native camera adapter (HW-003, PLAT-005). Stub for Phase 5.

Kept behind the common contract so Pi-specific APIs never leak into the
scientific core (PLAT-004: support without coupling).
"""

from __future__ import annotations

from typing import Any

from .base import CameraAdapter, FrameMetadata


class Picamera2Adapter(CameraAdapter):
    """Placeholder Raspberry Pi adapter; implemented in Migration Plan Phase 5."""

    def initialize(self) -> None:
        raise NotImplementedError("Raspberry Pi camera adapter is implemented in Phase 5.")

    def discover_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    def configure(self, **settings: Any) -> None:
        raise NotImplementedError

    def acquire_frame(self) -> tuple[Any, FrameMetadata]:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError
