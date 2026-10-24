"""Overlapping-line fitting (analysis.linefit): ground truth on known lines.

The doublet mimics Ar I 810.37 / 811.53 nm at 0.266 nm/px: 4.37 px apart with
4 px FWHM lines, which peak detection reports as a single line.
"""

import numpy as np
import pytest

import analysis.linefit as linefit
from analysis.linefit import fit_lines, refine_centers

C1 = 700.0
C2 = C1 + (811.531 - 810.369) / 0.266          # 704.37 px
SIGMA = 4.0 / 2.3548
X = np.arange(1280.0)


def _doublet(noise, seed):
    y = 10 + 100 * np.exp(-0.5 * ((X - C1) / SIGMA) ** 2) + 70 * np.exp(-0.5 * ((X - C2) / SIGMA) ** 2)
    return y + np.random.default_rng(seed).normal(0, noise, X.size)


def _errors(fit):
    return [abs(fit.lines[0].center_px - C1), abs(fit.lines[1].center_px - C2)]


def test_isolated_line_center_is_sub_pixel():
    true = 512.37
    y = 5 + 80 * np.exp(-0.5 * ((X - true) / SIGMA) ** 2)
    y = y + np.random.default_rng(3).normal(0, 1.0, X.size)
    fit = fit_lines(y, [512])
    assert len(fit.lines) == 1
    assert fit.lines[0].center_px == pytest.approx(true, abs=0.05)
    assert fit.lines[0].fwhm_px == pytest.approx(4.0, rel=0.05)
    assert fit.lines[0].amplitude == pytest.approx(80, rel=0.05)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_doublet_split_from_the_single_blend_peak(seed):
    fit = fit_lines(_doublet(2.0, seed), [702], n_lines=2, random_seed=seed)
    assert max(_errors(fit)) < 0.3
    assert fit.lines[0].center_px < fit.lines[1].center_px


def test_polish_tightens_doublet_centers():
    raw, polished = [], []
    for seed in range(5):
        y = _doublet(2.0, seed)
        raw += _errors(fit_lines(y, [702], n_lines=2, random_seed=seed, polish=False))
        polished += _errors(fit_lines(y, [702], n_lines=2, random_seed=seed, polish=True))
    assert np.mean(polished) < 0.5 * np.mean(raw)


def test_annealing_rescues_a_poor_start(monkeypatch):
    """From a seed 4 px off the blend, annealing+polish recovers the doublet far
    more often than the least-squares polish alone (README claim)."""
    def correct(fit):
        return max(_errors(fit)) < 0.5

    with_sa = sum(correct(fit_lines(_doublet(2.0, 100 + k), [706], n_lines=2, random_seed=k))
                  for k in range(10))

    def no_annealing(objective, x0, **kwargs):
        x0 = np.asarray(x0, dtype=float)
        return type("R", (), dict(x=x0, cost=float(objective(x0)), cycles=0,
                                  converged=False, history_cost=[]))()

    monkeypatch.setattr(linefit, "simulated_annealing", no_annealing)
    polish_only = sum(correct(fit_lines(_doublet(2.0, 100 + k), [706], n_lines=2, random_seed=k))
                      for k in range(10))
    assert with_sa >= 5
    assert polish_only <= 3
    assert with_sa > polish_only + 2


def test_reports_nm_when_given_a_wavelength_axis():
    wl = 600.0 + 0.266 * X
    fit = fit_lines(_doublet(1.0, 0), [702], n_lines=2, wavelengths=wl, random_seed=0)
    assert fit.lines[0].center_nm == pytest.approx(600 + 0.266 * C1, abs=0.03)
    assert fit.lines[1].center_nm == pytest.approx(600 + 0.266 * C2, abs=0.03)
    assert fit.lines[0].fwhm_nm == pytest.approx(4.0 * 0.266, rel=0.1)


def test_result_records_seed_method_and_model():
    y = _doublet(2.0, 0)
    fit = fit_lines(y, [702], n_lines=2, random_seed=11)
    assert fit.seed == 11
    assert fit.method in ("annealing+polish", "polish from seeds", "annealing")
    lo, hi = fit.window
    px = np.arange(lo, hi)
    assert np.sqrt(np.mean((fit.model(px) - y[lo:hi]) ** 2)) == pytest.approx(fit.rms_residual)
    assert fit.rms_residual < 3.0


def test_should_stop_cancels_promptly():
    fit = fit_lines(_doublet(2.0, 0), [702], n_lines=2, should_stop=lambda: True)
    assert fit.cycles <= 1


def test_progress_is_reported():
    seen = []
    fit_lines(_doublet(2.0, 0), [702], n_lines=2, progress=lambda c, n: seen.append((c, n)))
    assert seen and seen[0][0] == 1 and seen[0][1] == 200


def test_invalid_requests_are_rejected():
    y = _doublet(1.0, 0)
    with pytest.raises(ValueError):
        fit_lines(y, [])
    with pytest.raises(ValueError):
        fit_lines(y, [702], n_lines=3, window=(698, 706))
    with pytest.raises(ValueError):
        fit_lines([1.0, 2.0, 3.0], [1])


def test_refine_centers_fits_a_doublet_jointly_and_keeps_pick_order():
    y = _doublet(1.0, 0) + 90 * np.exp(-0.5 * ((X - 300.4) / SIGMA) ** 2)
    centers = refine_centers(y, [704, 300, 700], random_seed=0)
    assert centers[0] == pytest.approx(C2, abs=0.15)
    assert centers[1] == pytest.approx(300.4, abs=0.1)
    assert centers[2] == pytest.approx(C1, abs=0.15)


@pytest.mark.parametrize("sep", [8.0, 12.0, 16.0])
def test_two_lines_from_one_click_when_they_are_not_blended(sep):
    """Lines a few widths apart that peak detection labelled once (its minimum
    peak distance is 20 px): one click with 2 lines asked for still finds both."""
    c2 = C1 + sep
    y = 10 + 100 * np.exp(-0.5 * ((X - C1) / SIGMA) ** 2) + 70 * np.exp(-0.5 * ((X - c2) / SIGMA) ** 2)
    y = y + np.random.default_rng(4).normal(0, 2.0, X.size)
    fit = fit_lines(y, [700], n_lines=2, random_seed=0)
    assert fit.lines[0].center_px == pytest.approx(C1, abs=0.2)
    assert fit.lines[1].center_px == pytest.approx(c2, abs=0.2)
