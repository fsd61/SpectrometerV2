"""Ground truth for the extraction band: noise falls as 1/sqrt(rows).

Simulated OV9281-sized frames with independent per-pixel noise. Pins the
physics the feature relies on, and the reason slice_precision exists: with
integer truncation the gain from a tall band collapses.
Run scripts/measure_slice_height.py for the full table.
"""

import statistics

import pytest

from analysis.measurements import estimate_noise
from analysis.pipeline import analyze
from cameras.synthetic_camera import SyntheticCameraAdapter
from processing.extraction import extract_spectrum

LINES = [(400, 60.0, 4.0), (800, 120.0, 4.0)]


def _noise(rows, precision, frames=4, **cam):
    c = SyntheticCameraAdapter(width=1280, height=800, lines=LINES, baseline=10.0,
                               pixel_noise=3.0, slit_rows=401, seed=7, **cam)
    c.initialize()
    values = []
    for _ in range(frames):
        frame, _ = c.acquire_frame()
        values.append(estimate_noise(extract_spectrum(frame, average_rows=rows,
                                                      precision=precision).intensities))
    return statistics.median(values)


def test_noise_falls_as_one_over_root_rows():
    n3, n243 = _noise(3, "float"), _noise(243, "float")
    assert n3 / n243 == pytest.approx((243 / 3) ** 0.5, rel=0.15)   # ~9x


def test_integer_truncation_forfeits_most_of_the_gain():
    gain_float = _noise(3, "float") / _noise(243, "float")
    gain_int = _noise(3, "integer") / _noise(243, "integer")
    assert gain_float > 7.5
    assert gain_int < 4.0


def test_tall_band_does_not_improve_resolution_and_tilt_broadens():
    def fwhm(tilt):
        c = SyntheticCameraAdapter(width=1280, height=800, lines=LINES, baseline=10.0,
                                   pixel_noise=3.0, slit_rows=401, seed=7, tilt=tilt)
        c.initialize()
        frame, _ = c.acquire_frame()
        res = analyze(extract_spectrum(frame, average_rows=401, precision="float").intensities,
                      measure=True)
        return next(p.fwhm for p in res.peaks if abs(p.pixel - 800) <= 3)

    straight, tilted = fwhm(0.0), fwhm(0.01)      # 0.01 px/row = 4 px across 401 rows
    assert straight == pytest.approx(4.0, rel=0.05)   # the true line width, not narrower
    assert tilted > straight * 1.1
