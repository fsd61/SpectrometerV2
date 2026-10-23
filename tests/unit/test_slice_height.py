"""Configurable extraction band ("vertical slicing"): slice_height + slice_precision.

The defaults must reproduce PySpectrometer2 exactly (3 rows, integer); the new
options are opt-in, validated by the config layer, honored identically by the
GUI and the CLI, and recorded with every capture.
"""

import json

import numpy as np
import pytest

from acquisition.service import acquire_spectrum, extraction_settings
from app.main import main
from cameras.synthetic_camera import DEFAULT_LINES, SyntheticCameraAdapter
from config import load_config
from config.generate import render_ini
from errors import ConfigError
from processing.extraction import extract_intensity, extract_spectrum


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def test_float_precision_keeps_the_fraction():
    g = np.array([[1, 2], [2, 3], [4, 4]], dtype=np.uint8)
    out = extract_intensity(g, center_row=1, average_rows=3, precision="float")
    assert out.dtype == np.float64
    assert out.tolist() == pytest.approx([7 / 3, 3.0])
    # The baseline truncates the same band to whole counts.
    assert extract_intensity(g, center_row=1, average_rows=3).tolist() == [2, 3]


def test_tall_band_averages_every_row_in_it():
    g = np.zeros((101, 3))
    g[:, 0] = np.arange(101)          # mean of 0..100 = 50
    out = extract_intensity(g, average_rows=101, precision="float")
    assert out[0] == pytest.approx(50.0)


def test_unknown_precision_is_rejected():
    with pytest.raises(ValueError):
        extract_intensity(np.zeros((5, 4)), precision="double")


def test_band_taller_than_frame_is_rejected():
    with pytest.raises(ValueError):
        extract_intensity(np.zeros((9, 4)), average_rows=11)


def test_spectrum_records_band_and_precision():
    frame = np.full((21, 8), 7, dtype=np.uint8)
    spec = extract_spectrum(frame, average_rows=9, precision="float")
    assert spec.metadata["average_rows"] == 9
    assert spec.metadata["precision"] == "float"
    assert spec.metadata["extraction"] == "9-row-mean-float"
    assert all(isinstance(v, float) for v in spec.intensities)


def test_default_spectrum_is_unchanged_baseline():
    frame = np.full((21, 8), 7, dtype=np.uint8)
    spec = extract_spectrum(frame)
    assert spec.metadata["extraction"] == "3-row-mean"
    assert spec.metadata["precision"] == "integer"
    assert all(isinstance(v, int) for v in spec.intensities)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def test_defaults_match_pyspectrometer2():
    cfg = load_config()
    assert cfg.get("processing", "slice_height") == 3
    assert cfg.get("processing", "slice_precision") == "integer"


def test_even_slice_height_is_rejected_by_config():
    with pytest.raises(ConfigError, match="must be odd"):
        load_config(overrides=["processing.slice_height=10"])


def test_unknown_slice_precision_is_rejected_by_config():
    with pytest.raises(ConfigError):
        load_config(overrides=["processing.slice_precision=double"])


def test_generated_config_documents_the_odd_rule():
    ini = render_ini()
    assert "slice_height = 3" in ini and "odd" in ini


def test_extraction_settings_maps_the_processing_section():
    cfg = load_config(overrides=["processing.slice_row=200", "processing.slice_height=51",
                                 "processing.slice_precision=float"])
    assert extraction_settings(cfg.section("processing")) == {
        "center_row": 200, "average_rows": 51, "precision": "float"}


def test_extraction_settings_defaults_to_baseline():
    assert extraction_settings({}) == {"center_row": None, "average_rows": 3, "precision": "integer"}


def test_cli_run_honors_processing_settings(tmp_path):
    # Previously 'run' ignored [processing] entirely; it must match the GUI.
    rc = main(["--set", "logging.console=false", "--set", f"logging.directory={tmp_path}/logs",
               "--set", "camera.backend=synthetic", "--set", "processing.slice_height=21",
               "--set", "processing.slice_precision=float", "-o", str(tmp_path), "run"])
    assert rc == 0
    meta = json.loads((tmp_path / "acquisition.meta.json").read_text())
    assert meta["average_rows"] == 21 and meta["precision"] == "float"


# --------------------------------------------------------------------------- #
# Synthetic camera sensor realism
# --------------------------------------------------------------------------- #
def _frame(**kw):
    cam = SyntheticCameraAdapter(width=200, height=120, lines=[(100, 100.0, 6.0)], **kw)
    cam.initialize()
    return cam.acquire_frame()[0].astype(float)


def test_default_frames_are_unchanged():
    cam = SyntheticCameraAdapter(noise=2.0, seed=3)
    cam.initialize()
    frame, _ = cam.acquire_frame()
    x = np.arange(cam.width, dtype=float)
    profile = np.full(cam.width, cam.baseline)
    for c, a, w in DEFAULT_LINES:
        s = w / (2 * np.sqrt(2 * np.log(2)))
        profile += a * np.exp(-0.5 * ((x - c) / s) ** 2)
    profile = np.clip(profile, 0, 255)
    profile = np.clip(profile + np.random.default_rng(3).normal(0, 2.0, cam.width), 0, 255)
    assert np.array_equal(frame, np.tile(profile.astype(np.uint8), (cam.height, 1)))


def test_pixel_noise_is_independent_per_row():
    f = _frame(pixel_noise=3.0)
    assert not np.array_equal(f[10], f[11])


def test_slit_rows_light_only_the_slit_image():
    f = _frame(slit_rows=21)
    assert f[60, 100] > 50                    # center row, on the line
    assert f[0, 100] == pytest.approx(5.0)    # outside the slit: dark baseline only
    assert f[49, 100] == pytest.approx(5.0)   # first row above the 21-row slit image
    assert f[50, 100] > 50                    # first row inside it


def test_tilt_shifts_the_line_across_rows():
    f = _frame(tilt=0.1)
    assert int(np.argmax(f[110])) - int(np.argmax(f[10])) == pytest.approx(10, abs=1)


def test_acquire_spectrum_passes_band_and_precision():
    cam = SyntheticCameraAdapter(width=64, height=50, lines=[(32, 80.0, 5.0)])
    cam.initialize()
    spec = acquire_spectrum(cam, average_rows=25, precision="float")
    assert spec.metadata["average_rows"] == 25 and spec.metadata["precision"] == "float"
