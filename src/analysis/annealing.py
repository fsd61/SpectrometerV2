"""Simulated-annealing global optimizer (Migration Plan Phase 7 math).

Ported from the reference patch material (`Docs/reference/Patch_-_Wtx_+_SA/`),
based on DiGennaro & Cowburn, "Parametric Estimation of Time-Domain NMR Signals
Using Simulated Annealing", J. Magn. Reson. 96, 582-588 (1992), with four
practical refinements retained from that work:

1. Auto-tuned initial temperature ``T0`` targeting ~82% uphill acceptance.
2. Markov-chain length scaled by the number of spectral components.
3. A quench point that switches to pure iterative improvement for fast final
   convergence.
4. Threshold-based termination on the normalized error.

Modernization vs. the patch: diagnostics go through :mod:`logging` (not
``print``), a local seeded RNG is used instead of mutating global ``random`` /
``numpy`` state (so seeded runs are reproducible and never leak state between
callers), and the result is a typed :class:`AnnealingResult` dataclass.

``simulated_annealing`` minimizes an arbitrary ``objective(x) -> float``, so it
is not tied to any particular line model; :func:`gaussian_sum` and
:func:`sum_of_squares_objective` are provided as convenience helpers for the
common case of fitting a sum of Gaussians to a spectrum.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Cooling schedule presets: f(T0, cycle) -> T.
_SCHEDULES: dict[str, Callable[[float, int], float]] = {
    "fast": lambda T0, c: T0 / (1.0 + math.log(1.0 + c)),
    "medium": lambda T0, c: T0 * (0.90 ** c),
    "slow": lambda T0, c: T0 / (1.0 + 0.01 * c),
}


@dataclass
class AnnealingResult:
    """Outcome of a :func:`simulated_annealing` run."""

    x: np.ndarray            # best parameter vector found
    cost: float              # objective value at ``x``
    cycles: int              # temperature cycles completed
    markov_len: int          # inner Markov-chain length used
    T0: float                # initial temperature (auto-tuned or supplied)
    schedule: str            # schedule name ('fast'/'medium'/'slow'/'custom')
    quenched: bool           # whether the quench point was reached
    converged: bool          # whether the tolerance threshold was met
    history_cost: list = field(default_factory=list)  # best cost per cycle
    history_T: list = field(default_factory=list)      # temperature per cycle


def _tune_T0(
    objective: Callable[[np.ndarray], float],
    x0: Sequence[float],
    bounds: Optional[Sequence[Sequence[float]]],
    step_size: float,
    rng: random.Random,
    target_rate: float = 0.825,
    n_probe: int = 200,
) -> float:
    """Find an initial temperature giving ~``target_rate`` uphill acceptance."""
    x = np.array(x0, dtype=float)
    n = len(x)
    base_cost = float(objective(x))
    deltas: list[float] = []
    for _ in range(n_probe):
        xc = x + np.array([rng.uniform(-step_size, step_size) for _ in range(n)])
        if bounds is not None:
            for i, (lo, hi) in enumerate(bounds):
                xc[i] = max(lo, min(hi, xc[i]))
        delta = float(objective(xc)) - base_cost
        if delta > 0:
            deltas.append(delta)

    if not deltas:
        return 1.0  # landscape is (locally) convex — any small T will do

    mean_delta = float(np.mean(deltas))
    T0 = -mean_delta / math.log(target_rate)
    for _ in range(50):
        accepts = sum(1 for d in deltas if rng.random() < math.exp(-d / T0))
        if accepts / len(deltas) >= target_rate:
            break
        T0 *= 1.5
    return T0


def simulated_annealing(
    objective: Callable[[np.ndarray], float],
    x0: Sequence[float],
    *,
    schedule: str | Callable[[float, int], float] = "medium",
    T0: Optional[float] = None,
    n_components: Optional[int] = None,
    markov_factor: int = 600,
    quench_cycle: int = 12,
    quench_decrement: float = 0.70,
    tol: float = 1e-5,
    max_cycles: int = 200,
    step_size: float = 0.1,
    bounds: Optional[Sequence[Sequence[float]]] = None,
    random_seed: Optional[int] = None,
    callback: Optional[Callable[[int, np.ndarray, float, float], bool]] = None,
) -> AnnealingResult:
    """Minimize ``objective`` by simulated annealing. See module docstring.

    Leave ``T0=None`` to auto-tune the initial temperature (recommended). Set
    ``random_seed`` for reproducible runs. ``n_components`` (peak count) sets the
    Markov-chain length to ``markov_factor * n_components``; if ``None`` it
    defaults to a ``len(x0) // 3`` heuristic.
    """
    rng = random.Random(random_seed)

    if callable(schedule):
        cool, schedule_name = schedule, "custom"
    elif schedule in _SCHEDULES:
        cool, schedule_name = _SCHEDULES[schedule], schedule
    else:
        raise ValueError(
            f"Unknown schedule {schedule!r}. Choose from "
            f"{list(_SCHEDULES)} or pass a callable."
        )

    x_current = np.array(x0, dtype=float)
    n_params = len(x_current)
    if n_params == 0:
        raise ValueError("x0 is empty")
    cost_current = float(objective(x_current))
    cost_initial = cost_current

    if T0 is None:
        T0 = _tune_T0(objective, x0, bounds, step_size, rng)
        logger.debug("SA: auto-tuned T0 = %.4g (targeting ~82%% acceptance)", T0)
    T = T0

    if n_components is None:
        n_components = max(1, n_params // 3)
    markov_len = markov_factor * n_components
    logger.debug("SA: Markov chain length = %d (%d x %d)",
                 markov_len, markov_factor, n_components)

    work_bounds = [list(b) for b in bounds] if bounds is not None else None
    x_best = x_current.copy()
    cost_best = cost_current
    history_cost = [cost_best]
    history_T = [T0]
    quenched = converged = False

    def _clip(x: np.ndarray, wb) -> np.ndarray:
        if wb is None:
            return x
        for i, (lo, hi) in enumerate(wb):
            x[i] = max(lo, min(hi, x[i]))
        return x

    cycle = 0
    for cycle in range(1, max_cycles + 1):
        for _ in range(markov_len):
            perturb = np.array([rng.uniform(-step_size, step_size) for _ in range(n_params)])
            x_candidate = _clip(x_current + perturb, work_bounds)
            cost_cand = float(objective(x_candidate))
            delta = cost_cand - cost_current
            if delta < 0 or (T > 0 and rng.random() < math.exp(-delta / T)):
                x_current, cost_current = x_candidate, cost_cand
            if cost_current < cost_best:
                x_best, cost_best = x_current.copy(), cost_current

        history_cost.append(cost_best)
        history_T.append(T)

        R_e = abs(cost_best - cost_initial) / abs(cost_initial) if cost_initial != 0 else abs(cost_best)
        if cost_best <= tol or R_e >= (1.0 - tol):
            converged = True
            logger.debug("SA: converged at cycle %d (R_e=%.2e, cost=%.4g)",
                         cycle, R_e, cost_best)
            break

        if not quenched and cycle >= quench_cycle:
            quenched = True
            T = 0.0
            step_size *= (1.0 - quench_decrement)
            if work_bounds is not None:
                for i, (lo, hi) in enumerate(work_bounds):
                    span = (hi - lo) * (1.0 - quench_decrement) / 2.0
                    work_bounds[i] = [max(lo, x_best[i] - span), min(hi, x_best[i] + span)]
            logger.debug("SA: quench at cycle %d (cost=%.4g)", cycle, cost_best)
        elif not quenched:
            T = cool(T0, cycle)

        if callback is not None and callback(cycle, x_best.copy(), cost_best, T):
            break

    return AnnealingResult(
        x=x_best, cost=cost_best, cycles=cycle, markov_len=markov_len,
        T0=T0, schedule=schedule_name, quenched=quenched, converged=converged,
        history_cost=history_cost, history_T=history_T,
    )


# --------------------------------------------------------------------------- #
# Convenience helpers for the common "sum of Gaussians" fit
# --------------------------------------------------------------------------- #
def gaussian_sum(x: Sequence[float], params: Sequence[float]) -> np.ndarray:
    """Evaluate a sum of Gaussians on ``x``.

    ``params`` is a flat sequence ``[amp1, center1, sigma1, amp2, ...]`` — three
    values per peak.
    """
    x = np.asarray(x, dtype=float)
    params = np.asarray(params, dtype=float)
    if len(params) % 3 != 0:
        raise ValueError("params length must be a multiple of 3 (amp, center, sigma per peak)")
    y = np.zeros_like(x)
    for amp, center, sigma in params.reshape(-1, 3):
        if sigma == 0:
            continue
        y = y + amp * np.exp(-0.5 * ((x - center) / sigma) ** 2)
    return y


def sum_of_squares_objective(
    x: Sequence[float], y: Sequence[float]
) -> Callable[[np.ndarray], float]:
    """Build a least-squares objective for fitting :func:`gaussian_sum` to data.

    Returns ``f(params) -> mean squared residual`` suitable for
    :func:`simulated_annealing`.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    def objective(params: np.ndarray) -> float:
        residual = y - gaussian_sum(x, params)
        return float(np.mean(residual ** 2))

    return objective
