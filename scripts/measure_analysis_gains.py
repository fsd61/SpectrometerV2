"""Quantify what wavelet denoising and simulated-annealing line fitting add
over PySpectrometer2's analysis, on simulated spectra with known answers.

Three tests, each comparing against PySpectrometer2's own pipeline
(Savitzky-Golay 17/3 smoothing + peakutils peak picking, as preserved in
``analysis.pipeline.analyze``):

1. Line position accuracy vs SNR: PySpectrometer2's whole-pixel peak pick
   against the SA + least-squares fit, with the Cramer-Rao lower bound (the
   best any unbiased method can do) for reference.
2. Doublet resolution: how close two lines (100 : 70 height, like the Ar I
   810/811 nm pair) can be and still be split. PySpectrometer2 is given the
   best of its own settings; the fit is told there are two lines.
3. Weak-line detection: how often a faint line is found by peak picking on
   the smoothed spectrum, with and without wavelet denoising, with each
   pipeline's threshold set for the same false-alarm rate.

Lines are Gaussians 4 px FWHM (the OV9281 bench), SNR = line height / noise
standard deviation. Run from the repository root:

    python scripts/measure_analysis_gains.py [--quick] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analysis.linefit import fit_lines  # noqa: E402
from analysis.peaks import peak_indexes  # noqa: E402
from analysis.pipeline import analyze  # noqa: E402
from analysis.smoothing import savitzky_golay  # noqa: E402
from analysis.transforms import wavelet_denoise  # noqa: E402

N = 1280
X = np.arange(N, dtype=float)
FWHM = 4.0
SIG = FWHM / 2.3548
BASE = 10.0


def gauss(c, a):
    return a * np.exp(-0.5 * ((X - c) / SIG) ** 2)


def nearest(peaks, c):
    if len(peaks) == 0:
        return None
    p = min(peaks, key=lambda q: abs(q - c))
    return p


# --------------------------------------------------------------------------- #
# 1. Line position accuracy
# --------------------------------------------------------------------------- #
def crlb_center(snr, amp=100.0, half=12):
    """Cramer-Rao bound on the center (px) for a Gaussian line + constant
    baseline, all four parameters unknown, white noise."""
    x = np.arange(-half, half + 1, dtype=float)
    g = np.exp(-0.5 * (x / SIG) ** 2)
    J = np.column_stack([g, amp * g * x / SIG**2, amp * g * x**2 / SIG**3, np.ones_like(x)])
    sigma_n = amp / snr
    cov = sigma_n**2 * np.linalg.inv(J.T @ J)
    return float(np.sqrt(cov[1, 1]))


def test_position(snrs, trials, rng):
    rows = []
    for snr in snrs:
        err_pick, err_fit, miss = [], [], 0
        for t in range(trials):
            c = 640.0 + rng.uniform(0, 1)
            y = BASE + gauss(c, 100.0) + rng.normal(0, 100.0 / snr, N)
            peaks = [p.pixel for p in analyze(y).peaks]
            p = nearest(peaks, c)
            if p is None or abs(p - c) > 3:
                miss += 1
                continue
            err_pick.append(p - c)
            fit = fit_lines(y, [p], random_seed=t)
            err_fit.append(fit.lines[0].center_px - c)
        rms = lambda e: float(np.sqrt(np.mean(np.square(e)))) if e else float("nan")  # noqa: E731
        rows.append(dict(snr=snr, pick_rms=rms(err_pick), fit_rms=rms(err_fit),
                         crlb=crlb_center(snr), missed=miss, trials=trials))
    return rows


# --------------------------------------------------------------------------- #
# 2. Doublet resolution
# --------------------------------------------------------------------------- #
PS2_SETTINGS = [(order, md) for order in (3, 7, 11, 15) for md in (1, 3, 20)]


def ps2_resolves(y, c1, c2, order, min_dist, tol=1.0):
    sm = savitzky_golay(y, 17, order)
    peaks = peak_indexes(sm, thres=0.2, min_dist=min_dist)
    near = [p for p in peaks if c1 - 2 * FWHM <= p <= c2 + 2 * FWHM]
    if len(near) != 2:
        return False
    a, b = sorted(near)
    return abs(a - c1) <= tol and abs(b - c2) <= tol


def test_doublet(seps_fwhm, snrs, trials, rng):
    rows = []
    for snr in snrs:
        for sep in seps_fwhm:
            d = sep * FWHM
            ps2_default = 0
            ps2_by_setting = np.zeros(len(PS2_SETTINGS))
            sa_ok = 0
            sa_err = []
            for t in range(trials):
                c1 = 640.0 + rng.uniform(0, 1)
                c2 = c1 + d
                y = BASE + gauss(c1, 100.0) + gauss(c2, 70.0) + rng.normal(0, 100.0 / snr, N)
                ps2_default += ps2_resolves(y, c1, c2, 3, 20)
                for k, (order, md) in enumerate(PS2_SETTINGS):
                    ps2_by_setting[k] += ps2_resolves(y, c1, c2, order, md)
                # The fit, seeded as in the GUI: one click on the blend.
                peaks = [p.pixel for p in analyze(y).peaks]
                seed = nearest(peaks, (c1 + c2) / 2)
                if seed is None or abs(seed - (c1 + c2) / 2) > d / 2 + 4:
                    seed = int(np.argmax(y[int(c1) - 8:int(c2) + 8])) + int(c1) - 8
                fit = fit_lines(y, [seed], n_lines=2, random_seed=t)
                e1 = fit.lines[0].center_px - c1
                e2 = fit.lines[1].center_px - c2
                if abs(e1) <= 1.0 and abs(e2) <= 1.0:
                    sa_ok += 1
                    sa_err += [e1, e2]
            best = int(np.argmax(ps2_by_setting))
            rows.append(dict(
                snr=snr, sep_fwhm=sep, sep_px=d,
                ps2_default=ps2_default / trials,
                ps2_best=float(ps2_by_setting[best] / trials),
                ps2_best_setting=dict(order=PS2_SETTINGS[best][0], min_dist=PS2_SETTINGS[best][1]),
                sa=sa_ok / trials,
                sa_center_rms=float(np.sqrt(np.mean(np.square(sa_err)))) if sa_err else float("nan"),
            ))
    return rows


# --------------------------------------------------------------------------- #
# 3. Weak-line detection with and without wavelet denoising
# --------------------------------------------------------------------------- #
WEAK_C = 700.0
STRONG_C = 300.0
NOISE = 3.0
EMPTY = (450, 1200)      # region scanned for false peaks (weak line masked)


def _maxima_heights(sm):
    """Local maxima of a smoothed trace and their heights above its median."""
    peaks = peak_indexes(sm, thres=0.0, min_dist=1)
    base = float(np.median(sm))
    return np.asarray(peaks, dtype=int), sm[np.asarray(peaks, dtype=int)] - base if len(peaks) else np.array([])


_K = np.exp(-0.5 * (np.arange(-8, 9) / SIG) ** 2)
TRACES = {
    # PySpectrometer2's displayed/peak-picked trace.
    "smoothing": lambda y: savitzky_golay(y, 17, 3),
    # The v2.2.0 denoise stage ahead of the same smoothing.
    "wavelet": lambda y: savitzky_golay(wavelet_denoise(y).denoised, 17, 3),
    # Reference: correlating with the known line shape is the textbook optimal
    # detector for a known line in white noise.
    "matched": lambda y: np.convolve(y, _K / _K.sum(), mode="same"),
}


def test_detection(weak_snrs, trials, rng, false_rates=(0.01, 0.1, 1.0)):
    """Detection probability of a weak line, each trace's threshold set so it
    reports ``rate`` false peaks per 1000 px of empty spectrum."""
    # Calibrate thresholds on spectra with no weak line.
    heights = {name: [] for name in TRACES}
    span = 0
    for _ in range(2 * trials):
        y = BASE + gauss(STRONG_C, 100.0) + rng.normal(0, NOISE, N)
        for name, f in TRACES.items():
            p, h = _maxima_heights(f(y))
            heights[name].append(h[(p >= EMPTY[0]) & (p < EMPTY[1])])
        span += EMPTY[1] - EMPTY[0]
    thresholds = {}
    for name in TRACES:
        h = np.sort(np.concatenate(heights[name]))[::-1]
        thresholds[name] = {r: float(h[int(r * span / 1000.0)]) for r in false_rates}

    rows = []
    for s in weak_snrs:
        hits = {(name, r): 0 for name in TRACES for r in false_rates}
        for _ in range(trials):
            y = (BASE + gauss(STRONG_C, 100.0) + gauss(WEAK_C + rng.uniform(0, 1), s * NOISE)
                 + rng.normal(0, NOISE, N))
            for name, f in TRACES.items():
                p, h = _maxima_heights(f(y))
                near = np.abs(p - WEAK_C) <= 3
                top = float(np.max(h[near])) if np.any(near) else -np.inf
                for r in false_rates:
                    hits[(name, r)] += top > thresholds[name][r]
        rows.append(dict(weak_snr=s, **{f"{name}@{r}": hits[(name, r)] / trials
                                        for name in TRACES for r in false_rates}))
    return {"false_rates_per_1000px": list(false_rates), "rows": rows,
            "noise_spectra": 2 * trials, "span_px": span}


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quick", action="store_true", help="fewer trials, for a smoke run")
    ap.add_argument("--out", default="analysis_gains", help="output directory")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    n1, n2, n3 = (20, 10, 60) if args.quick else (200, 50, 500)

    t0 = time.time()
    results = {
        "position": test_position([3, 5, 10, 20, 50, 100, 300], n1, rng),
        "doublet": test_doublet([0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0], [20, 100], n2, rng),
        "detection": test_detection([1, 2, 3, 4, 5, 6, 8], n3, rng),
        "trials": dict(position=n1, doublet=n2, detection=n3),
        "seconds": None,
    }
    results["seconds"] = round(time.time() - t0, 1)
    (out / "results.json").write_text(json.dumps(results, indent=2))

    print("\n1. Line position, RMS error (px)")
    print(f"{'SNR':>5} {'PS2 pick':>9} {'SA fit':>8} {'CRLB':>7} {'missed':>7}")
    for r in results["position"]:
        print(f"{r['snr']:>5} {r['pick_rms']:>9.3f} {r['fit_rms']:>8.3f} {r['crlb']:>7.3f} "
              f"{r['missed']:>4}/{r['trials']}")
    print("\n2. Doublet resolved (fraction of trials)")
    print(f"{'SNR':>5} {'sep FWHM':>9} {'PS2 default':>12} {'PS2 best':>9} {'SA fit':>7} {'SA rms px':>10}")
    for r in results["doublet"]:
        print(f"{r['snr']:>5} {r['sep_fwhm']:>9.2f} {r['ps2_default']:>12.2f} {r['ps2_best']:>9.2f} "
              f"{r['sa']:>7.2f} {r['sa_center_rms']:>10.3f}")
    det = results["detection"]
    for rate in det["false_rates_per_1000px"]:
        print(f"\n3. Weak line detected (fraction), {rate} false peaks per 1000 px")
        print(f"{'SNR':>5} {'smoothing':>10} {'+wavelet':>9} {'matched':>8}")
        for r in det["rows"]:
            print(f"{r['weak_snr']:>5} {r[f'smoothing@{rate}']:>10.2f} "
                  f"{r[f'wavelet@{rate}']:>9.2f} {r[f'matched@{rate}']:>8.2f}")
    print(f"\n{results['seconds']} s; results in {out / 'results.json'}")


if __name__ == "__main__":
    main()
