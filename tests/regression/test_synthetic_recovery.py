"""Ground-truth recovery tests on deterministic synthetic spectra (Phase 1).

Unlike the characterization tests (which pin *whatever* the baseline produces),
these assert *correctness* against known synthetic truth: peak positions,
amplitude ordering, FWHM, and an SNR sanity relationship. They double as the
template the migrated ``analysis`` module must satisfy (TEST-002).
"""

import numpy as np
import pytest

from . import _baseline as B

# (center_px, amplitude, fwhm_px) — well separated relative to min_dist.
WELL_SEPARATED = [(100, 200.0, 6.0), (250, 150.0, 6.0), (430, 180.0, 7.0), (650, 120.0, 6.0)]


@pytest.fixture(scope="module")
def baseline():
    return B.load_baseline()


def test_recovers_known_peak_centers(baseline):
    _, y = B.synthetic_spectrum(width=800, lines=WELL_SEPARATED, baseline=5.0, noise=1.0, seed=7)
    smoothed = np.asarray(baseline.savitzky_golay(y, 17, 3), dtype=float)
    peaks = sorted(int(i) for i in np.asarray(
        baseline.peakIndexes(smoothed, thres=0.15, min_dist=20)))
    centers = [c for c, _, _ in WELL_SEPARATED]
    for c in centers:
        assert any(abs(p - c) <= 3 for p in peaks), f"missed center {c}; peaks={peaks}"
    assert len(peaks) == len(centers), f"unexpected peak count: {peaks}"


def test_amplitude_ordering_preserved(baseline):
    _, y = B.synthetic_spectrum(width=800, lines=WELL_SEPARATED, baseline=5.0, noise=0.0, seed=0)
    smoothed = np.asarray(baseline.savitzky_golay(y, 17, 3), dtype=float)
    peaks = sorted(int(i) for i in np.asarray(
        baseline.peakIndexes(smoothed, thres=0.1, min_dist=20)))
    measured_amps = [smoothed[p] for p in peaks]                 # in pixel order
    specified_amps = [a for _, a, _ in sorted(WELL_SEPARATED)]   # in pixel order
    assert list(np.argsort(measured_amps)) == list(np.argsort(specified_amps))


def test_fwhm_ground_truth_selfcheck():
    # Validates the fixture generator: half-max width of a noiseless Gaussian.
    width = 1200
    _, y = B.synthetic_spectrum(width=width, lines=[(600, 100.0, 20.0)], baseline=0.0, noise=0.0)
    peak = int(np.argmax(y))
    half = y[peak] / 2.0
    left = int(np.where(y[:peak] <= half)[0].max())
    right = peak + int(np.where(y[peak:] <= half)[0].min())
    assert (right - left) == pytest.approx(20.0, abs=1.0)


def test_snr_sanity_relationship(baseline):
    # SNR ~ amplitude / noise_sigma, estimated via MAD on a signal-free region.
    amp, sigma = 100.0, 5.0
    _, y = B.synthetic_spectrum(width=800, lines=[(400, amp, 8.0)], baseline=10.0, noise=sigma, seed=3)
    region = y[:200]  # no line here
    noise_est = np.median(np.abs(region - np.median(region))) / 0.6745
    snr = (np.max(y) - np.median(region)) / noise_est
    assert snr == pytest.approx(amp / sigma, rel=0.5)
