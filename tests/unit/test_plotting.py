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


def test_render_waterfall_labels_a_calibrated_axis_in_nm(tmp_path):
    frames = list(SyntheticStream(base=SPEC, drift_nm=2.0).iter_spectra(20))
    fig = render_waterfall(frames, path=None)
    labels = [t.get_text() for t in fig.axes[0].get_xticklabels()]
    assert all(lbl.endswith("nm") for lbl in labels if lbl)
    assert fig.axes[0].get_xlabel() == "wavelength (nm)"


def test_render_waterfall_falls_back_to_pixels_when_uncalibrated(tmp_path):
    """No calibration means no nm axis - not a stale or invented one."""
    from processing.spectrum import Spectrum

    frames = [Spectrum(wavelengths=[], intensities=[1.0, 5.0, 2.0, 8.0])
              for _ in range(4)]
    fig = render_waterfall(frames, path=None)
    assert fig.axes[0].get_xlabel() == "pixel"


def test_render_waterfall_honours_a_fixed_full_scale(tmp_path):
    frames = list(SyntheticStream(base=SPEC, drift_nm=2.0).iter_spectra(5))
    fig = render_waterfall(frames, path=None, full_scale=1023.0)
    assert fig.axes[0].images[0].get_clim() == (0.0, 1023.0)
