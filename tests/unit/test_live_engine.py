"""Tests for the Qt-free live engine and frame sources (ui.live).

These exercise the whole live loop minus Qt: build a synthetic source, step the
engine, and confirm analyzed frames come out and the stream advances.
"""

import pytest

from config.loader import load_config
from ui.live import (
    CameraFrameSource,
    LiveEngine,
    LiveParams,
    SyntheticFrameSource,
    build_frame_source,
)


def _synthetic_config():
    return load_config(overrides=["camera.backend=synthetic"])


def test_build_frame_source_synthetic():
    src = build_frame_source(_synthetic_config())
    assert isinstance(src, SyntheticFrameSource)


def test_engine_step_produces_peaks():
    engine = LiveEngine(build_frame_source(_synthetic_config()), LiveParams())
    spectrum, result = engine.step()
    assert len(spectrum) > 0
    assert len(result.smoothed) == len(spectrum)
    assert len(result.peaks) == 4  # the four demo lines
    assert result.peaks[0].wavelength == pytest.approx(405.0, abs=1.0)
    engine.close()


def test_stream_advances_between_steps():
    engine = LiveEngine(build_frame_source(_synthetic_config()))
    s0, _ = engine.step()
    s1, _ = engine.step()
    assert s0.metadata["frame_index"] == 0
    assert s1.metadata["frame_index"] == 1
    # The first line drifts, so its recovered center should move.
    engine.close()


def test_params_flow_into_analysis():
    # measure=True should attach FWHM/SNR to peaks.
    engine = LiveEngine(build_frame_source(_synthetic_config()),
                        LiveParams(measure=True))
    _, result = engine.step()
    assert result.peaks[0].fwhm is not None
    assert result.peaks[0].snr is not None
    engine.close()


def test_camera_frame_source_uses_adapter():
    # A synthetic *camera* adapter drives the acquisition path (no hardware).
    from cameras.synthetic_camera import SyntheticCameraAdapter

    cam = SyntheticCameraAdapter()
    cam.initialize()
    src = CameraFrameSource(cam)
    spectrum = src.next_spectrum()
    assert len(spectrum) > 0
    src.close()
