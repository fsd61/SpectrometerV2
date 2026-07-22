"""Platform acceptance smoke tests (Migration Plan Phase 8; ACC-001, TEST-001).

Runs the full stack on the *current* platform, hardware-free via the synthetic
camera: platform detection, acquisition, analysis, generation, and a
persist -> reload -> analyze roundtrip. On real Windows/Pi hardware the same
tests run against the USB/Pi adapters.
"""

import numpy as np

from acquisition.service import acquire_spectrum
from analysis.pipeline import analyze
from app.main import main
from cameras.synthetic_camera import SyntheticCameraAdapter, DEFAULT_LINES
from data.sinks import CsvSpectrumSink, read_csv_spectrum
from platforms import detect_platform
from synthetic.generator import SyntheticSpectrumSpec, generate


def test_platform_is_detected():
    info = detect_platform()
    assert info.system in {"linux", "windows", "macos", "unknown"}


def test_full_acquisition_pipeline_recovers_lines():
    cam = SyntheticCameraAdapter(noise=0.0)
    cam.initialize()
    try:
        spectrum = acquire_spectrum(cam)
    finally:
        cam.shutdown()
    result = analyze(spectrum.intensities, peak_thres=0.15, peak_min_dist=20, measure=True)
    pixels = sorted(p.pixel for p in result.peaks)
    for center, _amp, _fwhm in DEFAULT_LINES:
        assert any(abs(p - center) <= 2 for p in pixels)
    assert all(p.snr is not None for p in result.peaks)


def test_generate_persist_reload_analyze_roundtrip(tmp_path):
    spec = SyntheticSpectrumSpec(
        center_wavelengths=[405.0, 546.0], amplitudes=[200.0, 150.0],
        per_line_fwhm=[2.0, 3.0], snr=200.0, seed=1,
    )
    spectrum = generate(spec)
    path = CsvSpectrumSink(tmp_path).write(spectrum, name="acc")
    reloaded = read_csv_spectrum(path)
    assert np.allclose(reloaded.intensities, spectrum.intensities, atol=1e-9)
    result = analyze(reloaded.intensities, wavelengths=reloaded.wavelengths, peak_thres=0.1, peak_min_dist=10)
    got = sorted(round(p.wavelength) for p in result.peaks)
    assert 405 in got and 546 in got


def test_cli_run_smoke(tmp_path):
    rc = main([
        "--set", "camera.backend=synthetic",
        "--set", "logging.console=false", "--set", f"logging.directory={tmp_path}/logs",
        "-o", str(tmp_path), "run",
    ])
    assert rc == 0 and (tmp_path / "acquisition.csv").exists()
