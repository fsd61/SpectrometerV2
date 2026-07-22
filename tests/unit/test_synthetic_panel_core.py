"""Tests for the Qt-free synthetic-source panel core (ui.live)."""

import pytest

from analysis.pipeline import analyze
from synthetic.stream import SyntheticStream
from ui.live import (
    LiveEngine,
    LiveParams,
    SyntheticFrameSource,
    SyntheticPeak,
    build_synthetic_spec,
    spec_to_peaks,
)


def _source_from(peaks, **globals_):
    spec = build_synthetic_spec(peaks, **globals_)
    return SyntheticFrameSource(stream=SyntheticStream(base=spec, drift_nm=0.0))


def test_build_spec_maps_peaks_and_globals():
    peaks = [SyntheticPeak(450.0, 100.0, 2.0), SyntheticPeak(600.0, 50.0, 3.0)]
    spec = build_synthetic_spec(peaks, snr=80, baseline=5, sample_interval=0.5, seed=3)
    assert list(spec.center_wavelengths) == [450.0, 600.0]
    assert list(spec.amplitudes) == [100.0, 50.0]
    assert list(spec.per_line_fwhm) == [2.0, 3.0]
    assert spec.snr == 80 and spec.baseline == 5 and spec.seed == 3


def test_ground_truth_recovery():
    # The whole point of the panel: set peaks, pipeline recovers them.
    peaks = [SyntheticPeak(450.0, 120.0, 2.0), SyntheticPeak(600.0, 80.0, 2.5)]
    src = _source_from(peaks, snr=200, baseline=10, sample_interval=0.5, seed=1)
    spectrum, result = LiveEngine(src, LiveParams(measure=True)).step()
    centers = sorted(p.wavelength for p in result.peaks)
    assert len(centers) == 2
    assert centers[0] == pytest.approx(450.0, abs=1.0)
    assert centers[1] == pytest.approx(600.0, abs=1.0)


def test_set_spec_swaps_live():
    src = _source_from([SyntheticPeak(450.0, 100.0, 2.0)],
                       snr=200, baseline=0, sample_interval=0.5, seed=0)
    before = LiveEngine(src, LiveParams()).step()[1]
    assert len(before.peaks) == 1
    # Swap to three peaks; next frame reflects it.
    src.set_spec(build_synthetic_spec(
        [SyntheticPeak(430.0, 90.0, 2.0), SyntheticPeak(500.0, 90.0, 2.0),
         SyntheticPeak(650.0, 90.0, 2.0)],
        snr=200, baseline=0, sample_interval=0.5, seed=0))
    after = LiveEngine(src, LiveParams()).step()[1]
    assert len(after.peaks) == 3


def test_set_drift_toggles():
    src = _source_from([SyntheticPeak(450.0, 100.0, 2.0)],
                       snr=200, baseline=0, sample_interval=0.5, seed=0)
    src.set_drift(True, drift_nm=3.0)
    assert src.stream.drift_nm == 3.0
    src.set_drift(False)
    assert src.stream.drift_nm == 0.0


def test_spec_to_peaks_roundtrip():
    peaks = [SyntheticPeak(450.0, 100.0, 2.0), SyntheticPeak(600.0, 50.0, 3.0)]
    spec = build_synthetic_spec(peaks, snr=80, baseline=0, sample_interval=0.5, seed=0)
    back = spec_to_peaks(spec)
    assert [(p.wavelength, p.amplitude, p.fwhm) for p in back] == \
           [(450.0, 100.0, 2.0), (600.0, 50.0, 3.0)]
