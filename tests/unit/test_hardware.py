"""Unit tests for camera selection + on_missing policy (application layer)."""

import logging

import pytest

import app.hardware as hw
from cameras.synthetic_camera import SyntheticCameraAdapter
from config import load_config
from errors import CameraError

LOG = logging.getLogger("test")


def _cfg(**overrides):
    ov = [f"{k.replace('__', '.')}={v}" for k, v in overrides.items()]
    return load_config(overrides=ov)


@pytest.fixture(autouse=True)
def force_no_real_camera(monkeypatch):
    # Deterministic "no camera" path even if the test host has a webcam.
    monkeypatch.setattr(hw, "_try_real_camera", lambda section, logger: None)


def test_explicit_synthetic_is_simulated():
    cam, simulated = hw.select_camera(_cfg(camera__backend="synthetic"), LOG)
    assert isinstance(cam, SyntheticCameraAdapter) and simulated is True
    cam.shutdown()


def test_auto_error_policy_raises():
    with pytest.raises(CameraError):
        hw.select_camera(_cfg(camera__backend="auto", camera__on_missing="error"), LOG)


def test_auto_synthetic_policy_falls_back():
    cam, simulated = hw.select_camera(
        _cfg(camera__backend="auto", camera__on_missing="synthetic"), LOG)
    assert isinstance(cam, SyntheticCameraAdapter) and simulated is True
    cam.shutdown()


def test_auto_prompt_noninteractive_behaves_as_error():
    with pytest.raises(CameraError):
        hw.select_camera(_cfg(camera__backend="auto", camera__on_missing="prompt"),
                         LOG, isatty=False)


def test_auto_prompt_yes_falls_back_to_synthetic():
    cam, simulated = hw.select_camera(
        _cfg(camera__backend="auto", camera__on_missing="prompt"),
        LOG, isatty=True, prompt=lambda: True)
    assert simulated is True
    cam.shutdown()


def test_auto_prompt_no_raises():
    with pytest.raises(CameraError):
        hw.select_camera(_cfg(camera__backend="auto", camera__on_missing="prompt"),
                         LOG, isatty=True, prompt=lambda: False)


def test_none_backend_raises():
    with pytest.raises(CameraError):
        hw.select_camera(_cfg(camera__backend="none"), LOG)
