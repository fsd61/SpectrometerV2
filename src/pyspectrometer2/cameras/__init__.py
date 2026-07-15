"""Camera abstraction layer.

Defines the common camera contract and hosts platform/vendor adapters. Only
normalized frames and metadata cross this boundary; vendor-specific camera
objects never reach the scientific modules (Architecture §5; HW-001, HW-004).
"""

from .base import CameraAdapter, FrameMetadata

__all__ = ["CameraAdapter", "FrameMetadata"]
