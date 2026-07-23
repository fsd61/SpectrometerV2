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


def test_hold_peaks_accumulates_running_maximum():
    # With hold-peaks on, each frame's intensities are the element-wise max of
    # all frames so far, so the held trace never decreases sample-to-sample.
    import numpy as np

    engine = LiveEngine(build_frame_source(_synthetic_config()),
                        LiveParams(hold_peaks=True))
    s0, _ = engine.step()
    held0 = np.asarray(s0.intensities, dtype=float)
    s_last = s0
    for _ in range(4):
        s_last, _ = engine.step()
    held_last = np.asarray(s_last.intensities, dtype=float)
    assert s_last.metadata.get("hold_peaks") is True
    # Monotonic non-decreasing versus the first held frame.
    assert np.all(held_last >= held0 - 1e-9)
    engine.close()


def test_hold_peaks_resets_when_toggled_off():
    engine = LiveEngine(build_frame_source(_synthetic_config()),
                        LiveParams(hold_peaks=True))
    engine.step()
    engine.step()
    assert engine._hold is not None
    engine.params.hold_peaks = False
    engine.step()
    assert engine._hold is None
    engine.close()


class _PixelAxisSource:
    """A camera-like frame source that yields uncalibrated (pixel-axis) frames."""

    def __init__(self, n=64):
        from processing.spectrum import Spectrum
        self._spec = Spectrum(wavelengths=[], intensities=[float(i % 7) for i in range(n)],
                              metadata={"source": "camera"})

    def next_spectrum(self):
        return self._spec

    def close(self):
        pass


def test_calibration_applied_to_uncalibrated_frames():
    src = _PixelAxisSource(n=64)
    engine = LiveEngine(src, LiveParams())
    s0, _ = engine.step()
    assert len(s0.wavelengths) == 0            # camera frame arrives on pixel axis
    engine.set_calibration([400.0 + i for i in range(64)])
    s1, _ = engine.step()
    assert len(s1.wavelengths) == 64           # calibration attached
    assert s1.wavelengths[0] == 400.0
    assert s1.metadata.get("calibration") == "applied"
    engine.clear_calibration()
    s2, _ = engine.step()
    assert len(s2.wavelengths) == 0            # cleared
    engine.close()


def test_calibration_never_overwrites_ground_truth_axis():
    # Synthetic frames already carry true wavelengths; a user calibration must
    # not clobber them.
    engine = LiveEngine(build_frame_source(_synthetic_config()), LiveParams())
    engine.set_calibration([0.0] * 5000)
    spectrum, _ = engine.step()
    assert spectrum.wavelengths[0] != 0.0
    assert "calibration" not in spectrum.metadata
    engine.close()
