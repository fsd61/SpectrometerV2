"""Unit tests for the visualization module (Phase 7 rendering)."""

import pytest

pytest.importorskip("matplotlib")

from synthetic.generator import SyntheticSpectrumSpec, generate
from synthetic.stream import SyntheticStream
from analysis.pipeline import analyze
from ui.plotting import render_spectrum, render_waterfall

SPEC = SyntheticSpectrumSpec(center_wavelengths=[436.0, 546.0, 611.0],
                             amplitudes=[120.0, 180.0, 90.0], per_line_fwhm=[2.0, 3.0, 2.0],
                             snr=150.0, seed=1)


def test_render_spectrum_writes_png(tmp_path):
    sp = generate(SPEC)
    res = analyze(sp.intensities, wavelengths=sp.wavelengths, measure=True)
    path = render_spectrum(sp, res.peaks, path=tmp_path / "s.png")
    assert path.exists() and path.stat().st_size > 0


def test_render_waterfall_writes_png(tmp_path):
    frames = list(SyntheticStream(base=SPEC, drift_nm=2.0).iter_spectra(20))
    path = render_waterfall(frames, path=tmp_path / "w.png")
    assert path.exists() and path.stat().st_size > 0


def test_render_waterfall_empty_raises():
    with pytest.raises(ValueError):
        render_waterfall([], path=None)
