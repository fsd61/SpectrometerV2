"""Camera-contract conformance for every adapter (Architecture §8, Phase 5)."""

import pytest

from cameras import (
    CameraAdapter, Picamera2Adapter, SyntheticCameraAdapter, UsbCameraAdapter,
    create_camera, create_camera_from_config,
)
from errors import CameraError

ADAPTERS = [SyntheticCameraAdapter(), UsbCameraAdapter(), Picamera2Adapter()]
CONTRACT = ("initialize", "discover_capabilities", "configure", "acquire_frame", "status", "shutdown")


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: type(a).__name__)
def test_adapter_conforms_to_contract(adapter):
    assert isinstance(adapter, CameraAdapter)
    for method in CONTRACT:
        assert callable(getattr(adapter, method))


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: type(a).__name__)
def test_capabilities_are_a_mapping(adapter):
    caps = adapter.discover_capabilities()
    assert isinstance(caps, dict) and "backend" in caps


def test_factory_selects_backend():
    assert isinstance(create_camera("synthetic"), SyntheticCameraAdapter)
    assert isinstance(create_camera("usb"), UsbCameraAdapter)
    assert isinstance(create_camera("picamera2"), Picamera2Adapter)


def test_factory_unknown_backend_raises():
    with pytest.raises(CameraError):
        create_camera("nope")


def test_factory_from_config_defaults_to_usb():
    from config import load_config
    cfg = load_config("config/default.ini")
    cam = create_camera_from_config(cfg.section("camera"))
    assert isinstance(cam, UsbCameraAdapter) and cam.width == 1920
