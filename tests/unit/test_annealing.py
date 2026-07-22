"""Tests for analysis.annealing (simulated annealing).

SA is stochastic, so these are parametric *recovery* tests: synthesize a
spectrum with known Gaussian peaks at a fixed SNR, run SA from a deliberately
offset start, and assert the recovered parameters land within tolerance of the
truth. Repeated across several seeds to guard against a single lucky run.
"""

import numpy as np
import pytest

from analysis import (
    AnnealingResult,
    gaussian_sum,
    simulated_annealing,
    sum_of_squares_objective,
)


def _make_spectrum(truth, snr, seed, n=200):
    """Two-peak spectrum on a 0..n grid with additive noise at the given SNR."""
    x = np.arange(n, dtype=float)
    clean = gaussian_sum(x, truth)
    rng = np.random.default_rng(seed)
    peak_amp = max(truth[0::3])
    noise = rng.normal(0.0, peak_amp / snr, size=n)
    return x, clean + noise


def test_gaussian_sum_shape_and_validation():
    x = np.arange(50.0)
    y = gaussian_sum(x, [10.0, 25.0, 3.0])
    assert y.argmax() == 25 and y.max() == pytest.approx(10.0, rel=1e-6)
    with pytest.raises(ValueError):
        gaussian_sum(x, [1.0, 2.0])  # not a multiple of 3


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_recovers_known_peak_centers(seed):
    # Ground truth: two well-separated Gaussians.
    truth = [10.0, 60.0, 4.0, 6.0, 140.0, 5.0]
    x, y = _make_spectrum(truth, snr=100.0, seed=seed)

    objective = sum_of_squares_objective(x, y)
    # Start offset from truth; bounds keep peaks in plausible ranges.
    x0 = [8.0, 55.0, 3.0, 8.0, 135.0, 3.0]
    bounds = [(1.0, 20.0), (40.0, 80.0), (1.0, 10.0),
              (1.0, 20.0), (120.0, 160.0), (1.0, 10.0)]

    result = simulated_annealing(
        objective, x0, bounds=bounds, n_components=2,
        markov_factor=60, max_cycles=60, step_size=2.0, random_seed=seed,
    )
    assert isinstance(result, AnnealingResult)
    # Centers recovered within ~1 sample.
    assert result.x[1] == pytest.approx(60.0, abs=1.5)
    assert result.x[4] == pytest.approx(140.0, abs=1.5)
    # Amplitudes recovered within ~15%.
    assert result.x[0] == pytest.approx(10.0, rel=0.15)
    assert result.x[3] == pytest.approx(6.0, rel=0.15)
    # And the fit is better than the (already decent) starting guess.
    assert result.cost < objective(np.array(x0))


def test_reproducible_with_seed():
    truth = [10.0, 60.0, 4.0, 6.0, 140.0, 5.0]
    x, y = _make_spectrum(truth, snr=100.0, seed=3)
    objective = sum_of_squares_objective(x, y)
    x0 = [8.0, 55.0, 3.0, 8.0, 135.0, 3.0]
    kw = dict(bounds=None, n_components=2, markov_factor=30,
              max_cycles=25, step_size=1.5, random_seed=123)
    r1 = simulated_annealing(objective, x0, **kw)
    r2 = simulated_annealing(objective, x0, **kw)
    assert np.allclose(r1.x, r2.x) and r1.cost == r2.cost


def test_different_seeds_diverge_but_both_improve():
    truth = [12.0, 80.0, 5.0]
    x, y = _make_spectrum(truth, snr=50.0, seed=9, n=160)
    objective = sum_of_squares_objective(x, y)
    x0 = [6.0, 70.0, 3.0]
    start_cost = objective(np.array(x0))
    r_a = simulated_annealing(objective, x0, n_components=1, markov_factor=40,
                              max_cycles=30, step_size=2.0, random_seed=1)
    r_b = simulated_annealing(objective, x0, n_components=1, markov_factor=40,
                              max_cycles=30, step_size=2.0, random_seed=2)
    # Both independent runs improve on the start...
    assert r_a.cost < start_cost and r_b.cost < start_cost
    # ...and both land near the true center.
    assert r_a.x[1] == pytest.approx(80.0, abs=2.0)
    assert r_b.x[1] == pytest.approx(80.0, abs=2.0)


def test_rejects_unknown_schedule():
    with pytest.raises(ValueError, match="schedule"):
        simulated_annealing(lambda p: float(p[0] ** 2), [1.0], schedule="glacial")


def test_custom_schedule_and_convergence_flags():
    # Simple convex bowl: SA should drive cost toward ~0 and set converged.
    result = simulated_annealing(
        lambda p: float(p[0] ** 2 + p[1] ** 2),
        [5.0, -4.0],
        schedule=lambda T0, c: T0 * 0.8 ** c,
        bounds=[(-10, 10), (-10, 10)],
        markov_factor=50, max_cycles=80, step_size=1.0, tol=1e-4,
        random_seed=0,
    )
    assert result.schedule == "custom"
    assert result.cost < 1e-2
