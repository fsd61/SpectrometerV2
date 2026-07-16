"""Camera abstraction layer.

Defines the common camera contract and hosts platform/vendor adapters. Only
normalized frames and metadata cross this boundary; vendor-specific camera
objects never reach the scientific modules (Architecture §5; HW-001, HW-004).
"""

from .base import CameraAdapter, FrameMetadata
from .synthetic_camera import SyntheticCameraAdapter
from .usb import UsbCameraAdapter
from .picamera2 import Picamera2Adapter
from .factory import create_camera, create_camera_from_config

__all__ = [
    "CameraAdapter", "FrameMetadata",
    "SyntheticCameraAdapter", "UsbCameraAdapter", "Picamera2Adapter",
    "create_camera", "create_camera_from_config",
]
