"""Integration: frame -> extract -> calibrate -> analyze (Phase 3)."""

import numpy as np
import pytest

from processing.extraction import extract_spectrum
from calibration.wavelength import calibrate
from analysis.pipeline import analyze

LINES = [(120, 200, 8), (300, 120, 6), (410, 180, 10), (610, 90, 7)]
CAL_PIXELS = [35, 250, 470, 700]
CAL_WAVELENGTHS = [404.66, 435.83, 546.07, 611.60]


def _synthetic_frame(width=800, height=600):
    profile = np.full(width, 5.0)
    for center, amp, fwhm in LINES:
        profile += amp * np.exp(-0.5 * ((np.arange(width) - center) / fwhm) ** 2)
    return np.tile(profile, (height, 1))


def test_end_to_end_recovers_centers_and_wavelengths():
    spec = extract_spectrum(_synthetic_frame())
    cal = calibrate(CAL_PIXELS, CAL_WAVELENGTHS, len(spec))
    res = analyze(spec.intensities, wavelengths=cal.wavelengths,
                  peak_thres=0.15, peak_min_dist=20)
    pixels = sorted(p.pixel for p in res.peaks)
    centers = [c for c, _, _ in LINES]
    assert len(pixels) == len(centers)
    for c in centers:
        assert any(abs(p - c) <= 2 for p in pixels), f"missed {c}: {pixels}"
    for peak in res.peaks:
        assert peak.wavelength == pytest.approx(cal.wavelengths[peak.pixel], abs=1e-6)


def test_analyze_without_calibration_leaves_wavelength_none():
    spec = extract_spectrum(_synthetic_frame())
    res = analyze(spec.intensities, peak_thres=0.15, peak_min_dist=20)
    assert res.peaks and all(p.wavelength is None for p in res.peaks)
    assert len(res.smoothed) == len(spec)


def test_measure_populates_fwhm_snr_and_fwhm_nm():
    # In _synthetic_frame the third LINES value is the Gaussian sigma (px),
    # so the expected FWHM is 2.3548 * sigma.
    factor = 2.0 * np.sqrt(2.0 * np.log(2.0))
    spec = extract_spectrum(_synthetic_frame())
    cal = calibrate(CAL_PIXELS, CAL_WAVELENGTHS, len(spec))
    res = analyze(spec.intensities, wavelengths=cal.wavelengths,
                  peak_thres=0.15, peak_min_dist=20, measure=True)
    assert res.noise is not None and res.noise >= 0
    for center, _amp, sigma in LINES:
        peak = min(res.peaks, key=lambda q: abs(q.pixel - center))
        assert peak.fwhm == pytest.approx(factor * sigma, rel=0.15)
        assert peak.snr is not None and peak.snr > 0
        assert peak.fwhm_nm is not None and peak.fwhm_nm > 0
