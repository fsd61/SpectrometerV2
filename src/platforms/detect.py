"""Platform detection service (Architecture §4; PLAT-004, PLAT-007).

Uses the standard-library ``platform`` module (no longer shadowed now that this
package is ``platforms``). Keeps OS/hardware detection behind one boundary so the
scientific core stays platform-independent.
"""

from __future__ import annotations

import platform as _platform
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlatformInfo:
    system: str            # 'linux' | 'windows' | 'macos' | 'unknown'
    machine: str
    is_raspberry_pi: bool
    python_version: str
    node: str


def _normalize_system(name: str) -> str:
    name = (name or "").lower()
    if name.startswith("linux"):
        return "linux"
    if name.startswith("win"):
        return "windows"
    if name.startswith("darwin") or name == "mac":
        return "macos"
    return name or "unknown"


def _detect_raspberry_pi() -> bool:
    for candidate in ("/sys/firmware/devicetree/base/model", "/proc/device-tree/model"):
        try:
            if "raspberry pi" in Path(candidate).read_text(errors="ignore").lower():
                return True
        except OSError:
            pass
    try:
        info = Path("/proc/cpuinfo").read_text(errors="ignore").lower()
        if "raspberry pi" in info or "bcm27" in info or "bcm28" in info:
            return True
    except OSError:
        pass
    return False


def detect_platform() -> PlatformInfo:
    """Return normalized information about the current platform."""
    system = _normalize_system(_platform.system())
    is_pi = system == "linux" and _detect_raspberry_pi()
    return PlatformInfo(
        system=system,
        machine=_platform.machine(),
        is_raspberry_pi=is_pi,
        python_version=_platform.python_version(),
        node=_platform.node(),
    )


def recommended_camera_backend(info: PlatformInfo | None = None) -> str:
    """Pick a sensible default camera backend for the platform."""
    info = info or detect_platform()
    return "picamera2" if info.is_raspberry_pi else "usb"
