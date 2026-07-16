"""Unit tests for the platform detection service (Phase 6)."""

from platforms import PlatformInfo, detect_platform, recommended_camera_backend


def test_detect_platform_fields():
    info = detect_platform()
    assert isinstance(info, PlatformInfo)
    assert info.system in {"linux", "windows", "macos", "unknown"}
    assert isinstance(info.is_raspberry_pi, bool)
    assert info.python_version


def test_recommended_backend_is_known():
    assert recommended_camera_backend() in {"usb", "picamera2"}


def test_recommended_backend_follows_pi_flag():
    pi = PlatformInfo("linux", "aarch64", True, "3.11.0", "pi")
    pc = PlatformInfo("linux", "x86_64", False, "3.11.0", "pc")
    assert recommended_camera_backend(pi) == "picamera2"
    assert recommended_camera_backend(pc) == "usb"
