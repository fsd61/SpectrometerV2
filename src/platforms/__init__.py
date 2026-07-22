"""Platform-specific services (device discovery, paths, OS integration).

Linux, Windows, and Raspberry Pi are equal first-class targets. Platform-
specific behavior stays behind this boundary so the scientific core remains
OS-independent (PLAT-004, PLAT-007; Architecture §4).
"""

from .detect import PlatformInfo, detect_platform, recommended_camera_backend

__all__ = ["PlatformInfo", "detect_platform", "recommended_camera_backend"]
