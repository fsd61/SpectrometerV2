"""Integration: synthetic camera -> acquire -> extract -> analyze (Phase 5)."""

from acquisition.service import acquire_spectrum
from analysis.pipeline import analyze
from cameras.synthetic_camera import SyntheticCameraAdapter, DEFAULT_LINES


def test_acquire_and_analyze_recovers_lines():
    cam = SyntheticCameraAdapter(noise=0.0)
    cam.initialize()
    try:
        spectrum = acquire_spectrum(cam)
    finally:
        cam.shutdown()
    assert spectrum.metadata["frame"]["pixel_format"] == "GRAY"
    assert spectrum.metadata["frame"]["source"] == "synthetic"

    res = analyze(spectrum.intensities, peak_thres=0.15, peak_min_dist=20)
    pixels = sorted(p.pixel for p in res.peaks)
    for center, _amp, _fwhm in DEFAULT_LINES:
        assert any(abs(p - center) <= 2 for p in pixels), f"missed {center}: {pixels}"
