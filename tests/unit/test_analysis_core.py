"""Qt-free core of the analysis GUI: live denoise stage, live extraction band,
calibration A/B (leave-one-out), sub-pixel calibration files, the simulated
OV9281 backend, and the parameter objects behind the Analysis panel."""

import numpy as np
import pytest

from app.hardware import select_camera
from calibration.persistence import load_calibration_points, write_calibration_points
from calibration.wavelength import leave_one_out_residuals
from cameras.factory import create_camera
from cameras.synthetic_camera import OV9281_DEMO_LINES, ov9281_demo_camera
from config import load_config
from errors import CalibrationError
from ui.analysis_params import SAFitParams, WaveletParams
from ui.live import (CalibrationSession, CameraFrameSource, LiveEngine,
                     compare_centroid_methods)

LAW = lambda px: 600.0 + 0.266 * px + 2e-6 * px ** 2  # noqa: E731


def _camera_source(rows=3, precision="integer", seed=0):
    cam = ov9281_demo_camera(seed=seed)
    cam.initialize()
    return CameraFrameSource(cam, average_rows=rows, precision=precision)


# --------------------------------------------------------------------------- #
# Live denoise stage
# --------------------------------------------------------------------------- #
def test_denoise_stage_feeds_analysis_but_keeps_raw_spectrum():
    pytest.importorskip("pywt")
    engine = LiveEngine(_camera_source(), wavelet=WaveletParams(denoise=True))
    spectrum, result = engine.step()
    reference = _camera_source().next_spectrum()           # same seed, same frame
    assert list(spectrum.intensities) == list(reference.intensities)
    assert result.denoised is not None and len(result.denoised) == len(spectrum.intensities)
    assert spectrum.metadata["wavelet_denoise"]["mode"] == "hard"
    assert not np.allclose(result.denoised, spectrum.intensities)


def test_denoise_off_is_exactly_the_original_analysis():
    engine = LiveEngine(_camera_source(), wavelet=WaveletParams(denoise=False))
    spectrum, result = engine.step()
    assert result.denoised is None and "wavelet_denoise" not in spectrum.metadata


def test_denoise_failure_never_stops_capture():
    pytest.importorskip("pywt")
    engine = LiveEngine(_camera_source(), wavelet=WaveletParams(denoise=True, wavelet="nope"))
    spectrum, result = engine.step()
    assert engine.denoise_error and result.denoised is None and result.peaks


# --------------------------------------------------------------------------- #
# Live extraction band
# --------------------------------------------------------------------------- #
def test_set_extraction_applies_on_the_next_frame():
    src = _camera_source()
    src.next_spectrum()
    src.set_extraction(101, "float")
    spec = src.next_spectrum()
    assert spec.metadata["average_rows"] == 101 and spec.metadata["precision"] == "float"


@pytest.mark.parametrize("rows,precision", [(10, None), (0, None), (None, "double")])
def test_set_extraction_rejects_bad_values(rows, precision):
    src = _camera_source()
    with pytest.raises(ValueError):
        src.set_extraction(rows, precision)


def test_set_extraction_rejects_a_band_taller_than_the_frame():
    src = _camera_source()
    src.next_spectrum()                       # learns the 800-row frame
    assert src.max_band_height() == 799
    with pytest.raises(ValueError):
        src.set_extraction(801)
    assert src.average_rows == 3              # unchanged


# --------------------------------------------------------------------------- #
# Calibration A/B
# --------------------------------------------------------------------------- #
def test_leave_one_out_is_exact_for_points_on_a_cubic():
    px = [100.0, 300.0, 500.0, 700.0, 900.0, 1100.0]
    wl = [LAW(p) for p in px]
    assert np.max(np.abs(leave_one_out_residuals(px, wl))) < 1e-6


def test_leave_one_out_needs_four_points():
    with pytest.raises(CalibrationError):
        leave_one_out_residuals([1, 2, 3], [400, 500, 600])


def test_fitted_centers_beat_whole_pixel_picks():
    """The A/B: at the original 3-row extraction fitted centers already cut
    the leave-one-out error; with a tall float band the gain is large."""
    def mean_rms(rows, precision):
        picks, fitted = [], []
        for seed in range(3):
            session = CalibrationSession()
            for c, _a, _w in OV9281_DEMO_LINES:
                session.add(round(c), LAW(c))
            spec = _camera_source(rows, precision, seed).next_spectrum()
            comp = compare_centroid_methods(session, spec.intensities, random_seed=0)
            picks.append(comp.rms_pick)
            fitted.append(comp.rms_fitted)
        return np.mean(picks), np.mean(fitted)

    pick3, fit3 = mean_rms(3, "integer")
    pick101, fit101 = mean_rms(101, "float")
    assert fit3 < 0.85 * pick3
    assert fit101 < 0.2 * pick101


def test_session_fit_and_save_accept_fitted_pixels(tmp_path):
    session = CalibrationSession()
    for p in (100, 400, 700, 1000):
        session.add(p, LAW(p))
    fitted = [100.25, 400.5, 700.0, 999.75]
    assert session.fit(1280, pixels=fitted).wavelengths != session.fit(1280).wavelengths
    path = session.save(tmp_path / "cal.txt", pixels=fitted)
    pixels, _ = load_calibration_points(path)
    assert pixels == [100.25, 400.5, 700, 999.75]


def test_whole_pixel_files_keep_the_baseline_format(tmp_path):
    path = write_calibration_points(tmp_path / "c.txt", [35, 250, 470], [404.66, 435.83, 546.07])
    assert path.read_text().splitlines()[0] == "35,250,470"


# --------------------------------------------------------------------------- #
# Simulated OV9281 backend
# --------------------------------------------------------------------------- #
def test_synthetic_camera_backend_models_the_ov9281():
    cam = create_camera("synthetic-camera", width=1920, height=1080)
    cam.initialize()
    frame, meta = cam.acquire_frame()
    assert frame.shape == (800, 1280) and meta.extra["backend"] == "synthetic-camera"
    assert not np.array_equal(frame[400], frame[401])           # per-pixel noise


def test_synthetic_camera_backend_is_flagged_simulated():
    cfg = load_config(overrides=["camera.backend=synthetic-camera"])
    camera, simulated = select_camera(cfg, None)
    assert simulated is True
    camera.shutdown()


# --------------------------------------------------------------------------- #
# Panel parameter objects
# --------------------------------------------------------------------------- #
def test_wavelet_params_denoise_kwargs_and_config():
    p = WaveletParams.from_config({"wavelet": "coif3", "level": 3, "denoise": True,
                                   "threshold_mode": "soft", "threshold_scale": 1.0, "shifts": 4})
    assert p.denoise is True
    assert p.denoise_kwargs() == {"wavelet": "coif3", "level": 3, "threshold_scale": 1.0,
                                  "mode": "soft", "shifts": 4}
    p.set_threshold_scale(99)
    assert p.threshold_scale == WaveletParams.SCALE_MAX
    with pytest.raises(ValueError):
        p.set_threshold_mode("medium")


def test_wavelet_defaults_are_the_measured_safe_ones():
    p = WaveletParams()
    assert (p.wavelet, p.threshold_mode, p.threshold_scale, p.denoise) == ("sym5", "hard", 0.6, False)


def test_sa_fit_kwargs_map_onto_fit_lines():
    import inspect

    from analysis.linefit import fit_lines

    kwargs = SAFitParams(seed=7).fit_kwargs()
    assert set(kwargs) <= set(inspect.signature(fit_lines).parameters)
    assert kwargs["random_seed"] == 7 and kwargs["polish"] is True
    assert SAFitParams(lock_seed=False).fit_kwargs()["random_seed"] is None


def test_new_config_keys_load():
    cfg = load_config(overrides=["wavelet.denoise=true", "wavelet.threshold_mode=soft",
                                 "wavelet.threshold_scale=1.2", "wavelet.shifts=4"])
    assert cfg.get("wavelet", "denoise") is True
    assert cfg.get("wavelet", "threshold_scale") == pytest.approx(1.2)
