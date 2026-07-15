"""Generic USB / OpenCV-compatible camera adapter (HW-002). Stub for Phase 5."""

from __future__ import annotations

from typing import Any

from .base import CameraAdapter, FrameMetadata


class UsbCameraAdapter(CameraAdapter):
    """Placeholder USB adapter; implemented in Migration Plan Phase 5."""

    def __init__(self, device_index: int = 0):
        self.device_index = device_index

    def initialize(self) -> None:
        raise NotImplementedError("USB camera adapter is implemented in Phase 5.")

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
