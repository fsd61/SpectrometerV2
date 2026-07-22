"""The common camera contract (Architecture §5; HW-001..HW-004).

Every adapter (USB/OpenCV, Raspberry Pi native, synthetic) exposes the same
lifecycle so that acquisition and scientific code depend on this interface, not
on any specific camera API.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameMetadata:
    """Normalized, vendor-neutral description of a captured frame."""

    width: int
    height: int
    pixel_format: str
    extra: dict[str, Any] = field(default_factory=dict)


class CameraAdapter(abc.ABC):
    """Abstract camera adapter. Implementations live alongside this module."""

    @abc.abstractmethod
    def initialize(self) -> None:
        """Open the device and prepare it for acquisition."""

    @abc.abstractmethod
    def discover_capabilities(self) -> dict[str, Any]:
        """Return supported resolutions, formats, and other capabilities."""

    @abc.abstractmethod
    def configure(self, **settings: Any) -> None:
        """Apply resolution/exposure/gain and other supported settings."""

    @abc.abstractmethod
    def acquire_frame(self) -> tuple[Any, FrameMetadata]:
        """Capture one frame, returning a normalized array and its metadata."""

    @abc.abstractmethod
    def status(self) -> dict[str, Any]:
        """Return current health/status information."""

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Release the device cleanly."""
