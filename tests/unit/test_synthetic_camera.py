"""Unit tests for the synthetic camera adapter (Phase 5)."""

import numpy as np
import pytest

from cameras.synthetic_camera import SyntheticCameraAdapter
from errors import CameraError


def test_lifecycle_and_frame_shape():
    cam = SyntheticCameraAdapter(width=640, height=480, noise=0.0)
    cam.initialize()
    frame, meta = cam.acquire_frame()
    assert frame.shape == (480, 640) and frame.dtype == np.uint8
    assert meta.width == 640 and meta.height == 480 and meta.pixel_format == "GRAY"
    cam.shutdown()
    assert cam.status()["open"] is False


def test_bgr_format_has_three_channels():
    cam = SyntheticCameraAdapter(pixel_format="BGR")
    cam.initialize()
    frame, meta = cam.acquire_frame()
    assert frame.shape[2] == 3 and meta.pixel_format == "BGR"


def test_acquire_before_initialize_raises():
    with pytest.raises(CameraError):
        SyntheticCameraAdapter().acquire_frame()


def test_status_counts_frames():
    cam = SyntheticCameraAdapter()
    cam.initialize()
    cam.acquire_frame()
    cam.acquire_frame()
    assert cam.status()["frames_acquired"] == 2


def test_configure_changes_resolution():
    cam = SyntheticCameraAdapter()
    cam.configure(width=1024, height=768)
    cam.initialize()
    _, meta = cam.acquire_frame()
    assert (meta.width, meta.height) == (1024, 768)


def test_capabilities_report_backend():
    caps = SyntheticCameraAdapter().discover_capabilities()
    assert caps["backend"] == "synthetic" and "GRAY" in caps["formats"]
