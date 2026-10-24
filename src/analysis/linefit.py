"""Overlapping-line fitting by simulated annealing (GUI line fitting, A/B check).

Fits a sum of Gaussians plus a linear local baseline to a small pixel window
around one or more lines, using the project's simulated-annealing optimizer
(:func:`analysis.annealing.simulated_annealing`, after DiGennaro & Cowburn,
J. Magn. Reson. 96, 582-588, 1992). Its job is to split lines that peak
detection cannot — the Ar I 810.37 / 811.53 nm doublet is ~4.4 px apart at
0.266 nm/px, about one line width — and to give sub-pixel line centers.

Practical choices, all documented on :func:`fit_lines`:

* The fit runs on a window, not the whole spectrum, and in normalized units
  (amplitudes as a fraction of the window's peak, positions and widths in
  pixels), so one ``step_size`` suits every parameter.
* The local baseline is a straight line through the window's end samples and is
  subtracted before fitting.
* The optimizer's own stopping rule (a relative cost reduction of 1 - tol)
  essentially never fires on noisy data, because the residual cannot fall below
  the noise. After the quench point the run therefore also stops once the best
  cost has stalled for ``stall_cycles`` cycles, which is what makes the fit fast
  enough for interactive use.
* Annealing finds the right basin; a Levenberg-Marquardt polish from there then
  converges to the exact least-squares minimum. A polish straight from the seeds
  is also tried and the lowest residual wins; ``LineFitResult.method`` records
  which path that was. Annealing's random steps settle
  slowly on strongly coupled parameters such as a blended doublet's, so without
  the polish centers scatter by several tenths of a pixel.
* Results are sorted by center (SA can return lines in any order) and the seed
  is recorded, so a fit is reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from .annealing import gaussian_sum, simulated_annealing, sum_of_squares_objective
from .measurements import half_max_fwhm

FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))


@dataclass
class FittedLine:
    """One fitted line. Pixel quantities always; nm when a wavelength axis is given."""

    center_px: float
    amplitude: float              # counts above the local baseline
    sigma_px: float
    fwhm_px: float
    center_nm: Optional[float] = None
    fwhm_nm: Optional[float] = None


@dataclass
class LineFitResult:
    """Outcome of :func:`fit_lines`."""

    lines: list                   # list[FittedLine], sorted by center
    window: tuple                 # (lo, hi) pixel range fitted, hi exclusive
    baseline: tuple               # (value at lo, slope per pixel), counts
    rms_residual: float           # counts
    cycles: int
    stopped_early: bool           # stalled / converged rather than out of budget
    seed: Optional[int]
    polished: bool = False        # Levenberg-Marquardt refinement applied
    # Which candidate won (lowest residual): 'annealing+polish', 'annealing',
    # or 'polish from seeds' (annealing was not needed for this fit).
    method: str = "annealing"
    cost_history: list = field(default_factory=list)

    def baseline_at(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        return self.baseline[0] + self.baseline[1] * (x - self.window[0])

    def components(self, x) -> list:
        """Each line alone (counts, without baseline) evaluated at pixels ``x``."""
        x = np.asarray(x, dtype=float)
        return [gaussian_sum(x, [ln.amplitude, ln.center_px, ln.sigma_px]) for ln in self.lines]

    def model(self, x) -> np.ndarray:
        """Baseline plus all lines, in counts, at pixels ``x``."""
        x = np.asarray(x, dtype=float)
        total = self.baseline_at(x)
        for comp in self.components(x):
            total = total + comp
        return total


def _polish(x, y, p0, bounds, max_iter: int = 100):
    """Levenberg-Marquardt refinement of a Gaussian-sum fit (NumPy only).

    Annealing finds the right basin but its random steps settle slowly when
    parameters are strongly coupled, as a blended doublet's are. Starting from
    the annealing result, this deterministic least-squares step converges to
    the exact local minimum, using the analytic Jacobian. Bounds are enforced
    by clipping. Returns the polished parameters and their sum of squares.
    """
    p = np.asarray(p0, dtype=float).copy()
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)

    def residual_and_jacobian(q):
        r = y.copy()
        J = np.empty((len(x), len(q)))
        for k in range(0, len(q), 3):
            a, c, s = q[k], q[k + 1], max(q[k + 2], 1e-6)
            d = x - c
            g = np.exp(-0.5 * (d / s) ** 2)
            r -= a * g
            J[:, k] = g
            J[:, k + 1] = a * g * d / s ** 2
            J[:, k + 2] = a * g * d ** 2 / s ** 3
        return r, J

    r, J = residual_and_jacobian(p)
    cost = float(r @ r)
    lam = 1e-3
    for _ in range(max_iter):
        JtJ = J.T @ J
        g = J.T @ r
        step = np.linalg.solve(JtJ + lam * np.diag(np.diag(JtJ) + 1e-12), g)
        trial = np.clip(p + step, lo, hi)
        r_t, J_t = residual_and_jacobian(trial)
        cost_t = float(r_t @ r_t)
        if cost_t < cost:
            converged = (cost - cost_t) <= 1e-12 * max(cost, 1e-30)
            p, r, J, cost = trial, r_t, J_t, cost_t
            lam = max(lam / 3.0, 1e-12)
            if converged:
                break
        else:
            lam *= 4.0
            if lam > 1e12:
                break
    return p, cost


def _seed_width(y: np.ndarray, seeds: Sequence[float]) -> float:
    """Half-max width (px) at the strongest seed."""
    idx = int(max(seeds, key=lambda s: y[int(round(s))]))
    try:
        return float(half_max_fwhm(y, int(round(idx))))
    except ValueError:
        return 4.0


def _initial_sigma(y: np.ndarray, seeds: Sequence[float], n_lines: int) -> float:
    """Rough per-line sigma: the half-max width at the strongest seed, shared
    between the lines a blend may contain."""
    groups = max(1, n_lines - len(seeds) + 1)
    return float(np.clip(_seed_width(y, seeds) / groups / FWHM_PER_SIGMA, 0.5, 10.0))


def _maxima_positions(y: np.ndarray, seeds: Sequence[float], n_lines: int,
                      width: float) -> Optional[list]:
    """Start positions from the local maxima near the seeds.

    For lines asked for beyond the seeds that are *not* blended -- e.g. two
    lines 10 px apart that peak detection labelled once because of its
    minimum peak distance -- starting them one sigma either side of the seed
    leaves the second line out of reach. Here the data are lightly smoothed,
    local maxima within a few line widths of the seeds that stand clear of the
    noise are taken strongest first, and any lines still missing are spread
    around the strongest one. Returns None when no extra maximum is found.
    """
    n = len(y)
    # Peak detection's default minimum distance is 20 px, so a second line can
    # hide up to 20 px from the labelled one; search a little beyond that.
    reach = max(24.0, 3.0 * width)
    lo = max(1, int(math.floor(min(seeds) - reach)))
    hi = min(n - 1, int(math.ceil(max(seeds) + reach)) + 1)
    if hi - lo < 5:
        return None
    k = np.exp(-0.5 * (np.arange(-3, 4) / 1.0) ** 2)
    sm = np.convolve(y, k / k.sum(), mode="same")
    noise = float(np.median(np.abs(np.diff(y))) / 0.6745 / math.sqrt(2.0)) or 1e-12
    seg = sm[lo:hi]
    floor = float(np.median(seg))
    cand = [i for i in range(lo + 1, hi - 1)
            if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] - floor > 4.0 * noise]
    cand.sort(key=lambda i: sm[i], reverse=True)
    picked: list = []
    for i in cand:
        if all(abs(i - j) >= max(2.0, width / 2.0) for j in picked):
            picked.append(i)
        if len(picked) == n_lines:
            break
    if len(picked) <= len(seeds):
        return None
    sigma = width / FWHM_PER_SIGMA
    while len(picked) < n_lines:              # still short: spread round the strongest
        picked.append(picked[0] + sigma * (1 if len(picked) % 2 else -1))
    return sorted(float(p) for p in picked)


def _seed_positions(seeds: Sequence[float], n_lines: int, sigma: float) -> list:
    """Start positions for ``n_lines`` lines from fewer (or equal) seeds.

    Extra lines are spread around the seeds: a single seed asked for two lines
    starts them one sigma either side, which is where a blended doublet's
    components sit.
    """
    seeds = sorted(float(s) for s in seeds)
    if n_lines <= len(seeds):
        return seeds[:n_lines]
    lo, hi = seeds[0] - sigma, seeds[-1] + sigma
    return list(np.linspace(lo, hi, n_lines))


def fit_lines(
    intensities: Sequence[float],
    seeds_px: Sequence[float],
    *,
    n_lines: Optional[int] = None,
    window: Optional[tuple] = None,
    wavelengths: Optional[Sequence[float]] = None,
    bound_tightness: float = 0.5,
    schedule: str = "medium",
    max_cycles: int = 200,
    tol: float = 1e-5,
    markov_factor: int = 600,
    step_size: float = 0.1,
    quench_cycle: int = 12,
    random_seed: Optional[int] = 0,
    stall_cycles: int = 8,
    stall_rtol: float = 1e-6,
    polish: bool = True,
    progress: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> LineFitResult:
    """Fit ``n_lines`` Gaussians near ``seeds_px`` by simulated annealing.

    Args:
        intensities: the spectrum (counts per pixel).
        seeds_px: approximate line centers in pixels (detected peaks or clicks).
        n_lines: how many lines to fit; defaults to ``len(seeds_px)``. Ask for
            more lines than seeds to split a blend peak detection saw as one.
        window: ``(lo, hi)`` pixel range to fit; default spans the seeds plus
            about four line widths either side.
        wavelengths: per-pixel wavelength axis; if given, centers and widths
            are also reported in nm.
        bound_tightness: 0 = centers may wander ~7 px from their seeds,
            1 = ~1 px.
        schedule, max_cycles, tol, markov_factor, step_size, quench_cycle,
        random_seed: passed to the annealing optimizer (``random_seed=None``
            gives a fresh, unrecorded run).
        stall_cycles, stall_rtol: after the quench, stop once the best cost has
            improved by less than ``stall_rtol`` (relative) over this many cycles.
        polish: refine the annealing result with Levenberg-Marquardt (kept only
            if it lowers the residual). Annealing locates the lines; the polish
            pins down their centers to the precision the noise allows.
        progress: called as ``progress(cycle, max_cycles)`` each cycle.
        should_stop: polled each cycle; returning True cancels the run.
    """
    y_all = np.asarray(intensities, dtype=float)
    n = len(y_all)
    if n < 5:
        raise ValueError("spectrum too short to fit")
    if not seeds_px:
        raise ValueError("at least one seed position is required")
    n_lines = int(n_lines or len(seeds_px))
    if n_lines < 1:
        raise ValueError("n_lines must be at least 1")

    sigma0 = _initial_sigma(y_all, seeds_px, n_lines)
    # Start arrangements to try. The first assumes the extra lines hide in a
    # blend around the seeds; when more lines are asked for than seeds, the
    # local maxima nearby give a second arrangement, for lines that are
    # separate but were labelled as one peak. The lowest residual wins.
    start_sets = [(_seed_positions(seeds_px, n_lines, sigma0), sigma0)]
    if n_lines > len(seeds_px):
        width = _seed_width(y_all, seeds_px)
        alt = _maxima_positions(y_all, seeds_px, n_lines, width)
        if alt is not None and np.max(np.abs(np.array(alt) - np.array(start_sets[0][0]))) > 1.0:
            start_sets.append((alt, float(np.clip(width / FWHM_PER_SIGMA, 0.5, 10.0))))
    all_starts = [c for starts, _s in start_sets for c in starts]

    if window is None:
        margin = max(6, int(math.ceil(4 * sigma0 * FWHM_PER_SIGMA / 2)) + 4)
        window = (int(math.floor(min(all_starts))) - margin,
                  int(math.ceil(max(all_starts))) + margin + 1)
    lo, hi = max(0, int(window[0])), min(n, int(window[1]))
    if hi - lo < 3 * n_lines + 2:
        raise ValueError("fit window too small for the requested number of lines")

    x = np.arange(lo, hi, dtype=float)
    y = y_all[lo:hi]
    edge = max(2, min(4, (hi - lo) // 8))
    b0 = float(np.mean(y[:edge]))
    b1 = float(np.mean(y[-edge:]))
    slope = (b1 - b0) / max(1.0, float(hi - lo - edge))
    baseline = b0 + slope * (x - lo - (edge - 1) / 2.0)
    signal = y - baseline
    scale = float(max(np.max(signal), 1e-9))
    y_norm = signal / scale

    reach = 1.0 + 6.0 * (1.0 - float(np.clip(bound_tightness, 0.0, 1.0)))
    objective = sum_of_squares_objective(x, y_norm)

    def _run(starts, sigma_start):
        """Anneal (and polish) from one start arrangement."""
        x0, bounds = [], []
        for c in starts:
            amp = float(np.clip(np.interp(c, x, y_norm), 0.05, 1.2))
            x0 += [amp, float(c), sigma_start]
            bounds += [(0.0, 1.5), (max(lo, c - reach), min(hi - 1, c + reach)),
                       (0.3, max(2.0, (hi - lo) / 4.0))]
        history: list = []
        state = {"stopped_early": False}

        def _callback(cycle, x_best, cost_best, T):
            history.append(float(cost_best))
            if progress is not None:
                progress(cycle, max_cycles)
            if should_stop is not None and should_stop():
                return True
            if cycle > quench_cycle and len(history) > stall_cycles:
                past = history[-stall_cycles - 1]
                if past <= 0 or (past - cost_best) / past < stall_rtol:
                    state["stopped_early"] = True
                    return True
            return False

        res = simulated_annealing(
            objective, x0, schedule=schedule, n_components=n_lines,
            markov_factor=markov_factor, quench_cycle=quench_cycle, tol=tol,
            max_cycles=max_cycles, step_size=step_size, bounds=bounds,
            random_seed=random_seed, callback=_callback,
        )
        # Candidates, kept by lowest mean squared residual: the annealing
        # result, the annealing result polished, and a polish straight from the
        # starts. The last guards against annealing settling in a wrong
        # arrangement (seen with short chains on very high-SNR doublets);
        # annealing in turn rescues starts the polish alone cannot (e.g. seeds
        # several pixels off).
        best, best_cost, method = np.asarray(res.x, dtype=float), float(res.cost), "annealing"
        if polish:
            for start, label in ((best, "annealing+polish"),
                                 (np.asarray(x0, dtype=float), "polish from seeds")):
                refined, cost = _polish(x, y_norm, start, bounds)
                if cost / len(x) < best_cost:
                    best, best_cost, method = refined, cost / len(x), label
        return best, best_cost, method, res, state["stopped_early"]

    outcome = None
    for starts, sigma_start in start_sets:
        run = _run(starts, sigma_start)
        if outcome is None or run[1] < outcome[1]:
            outcome = run
        if should_stop is not None and should_stop():
            break
    best, best_cost, method, res, stalled = outcome
    polished = method != "annealing"
    params = best.reshape(-1, 3)
    wl = np.asarray(wavelengths, dtype=float) if wavelengths is not None and len(wavelengths) >= n else None
    dispersion = np.gradient(wl) if wl is not None else None
    lines = []
    for amp, center, sigma in params:
        sigma = abs(float(sigma))
        line = FittedLine(center_px=float(center), amplitude=float(amp) * scale,
                          sigma_px=sigma, fwhm_px=sigma * FWHM_PER_SIGMA)
        if wl is not None:
            line.center_nm = float(np.interp(center, np.arange(n), wl))
            line.fwhm_nm = line.fwhm_px * abs(float(np.interp(center, np.arange(n), dispersion)))
        lines.append(line)
    lines.sort(key=lambda ln: ln.center_px)

    result = LineFitResult(
        lines=lines, window=(lo, hi),
        baseline=(float(b0 - slope * (edge - 1) / 2.0), float(slope)),
        rms_residual=0.0, cycles=int(res.cycles),
        stopped_early=bool(stalled or res.converged),
        seed=random_seed, polished=polished, method=method,
        cost_history=list(res.history_cost),
    )
    result.rms_residual = float(np.sqrt(np.mean((y - result.model(x)) ** 2)))
    return result


def refine_centers(
    intensities: Sequence[float],
    picks_px: Sequence[float],
    *,
    merge_px: float = 10.0,
    **fit_kwargs,
) -> list:
    """Sub-pixel centers for calibration picks, in the order given.

    Picks closer than ``merge_px`` are fitted together as one blend (one line
    per pick), so the two halves of a doublet are separated rather than each
    fitted as if it were alone. ``fit_kwargs`` go to :func:`fit_lines`.
    """
    order = sorted(range(len(picks_px)), key=lambda i: float(picks_px[i]))
    groups: list = []
    for i in order:
        if groups and float(picks_px[i]) - float(picks_px[groups[-1][-1]]) <= merge_px:
            groups[-1].append(i)
        else:
            groups.append([i])
    centers = [0.0] * len(picks_px)
    for group in groups:
        seeds = [float(picks_px[i]) for i in group]
        fit = fit_lines(intensities, seeds, n_lines=len(group), **fit_kwargs)
        for i, line in zip(group, fit.lines):     # both sorted by position
            centers[i] = line.center_px
    return centers
