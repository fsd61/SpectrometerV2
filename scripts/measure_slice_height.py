"""Measure what a taller extraction band (slice_height) buys, on simulated frames.

Renders OV9281-sized frames (1280 x 800, 8-bit) with the synthetic camera's
sensor-realistic options -- independent per-pixel noise, a slit image of finite
height, optional slit tilt -- then extracts spectra exactly as the application
does and measures them with the application's own analysis code:

* noise  -- robust noise sigma of the extracted spectrum (estimate_noise)
* SNR    -- peak height above baseline / noise, for each line (estimate_snr)
* FWHM   -- Gaussian-fit line width in pixels

Every number is the median over several independently-seeded frames.
These are simulated results under stated assumptions, not hardware
measurements; re-run with your own camera's numbers via the options below.

Usage:
    python scripts/measure_slice_height.py
    python scripts/measure_slice_height.py --pixel-noise 2 --slit-rows 300 --tilt 0.01
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from analysis.pipeline import analyze  # noqa: E402
from cameras.synthetic_camera import SyntheticCameraAdapter  # noqa: E402
from processing.extraction import extract_spectrum  # noqa: E402

# Lines in pixel space: (center_px, amplitude_counts, fwhm_px). Deliberately dim,
# because SNR matters most for weak lines.
LINES = [(300, 40.0, 4.0), (640, 20.0, 4.0), (980, 60.0, 4.0)]


def measure(rows: int, precision: str, tilt: float, args) -> dict:
    cam = SyntheticCameraAdapter(
        width=1280, height=800, lines=LINES, baseline=args.baseline,
        pixel_noise=args.pixel_noise, slit_rows=args.slit_rows, tilt=tilt, seed=args.seed,
    )
    cam.initialize()
    noise, snr, fwhm = [], {c: [] for c, _, _ in LINES}, {c: [] for c, _, _ in LINES}
    for _ in range(args.frames):
        frame, _meta = cam.acquire_frame()
        spec = extract_spectrum(frame, average_rows=rows, precision=precision)
        result = analyze(spec.intensities, measure=True, peak_thres=0.15)
        noise.append(result.noise)
        for center, _amp, _w in LINES:
            near = [p for p in result.peaks if abs(p.pixel - center) <= 6]
            if near:
                p = max(near, key=lambda q: q.intensity)
                if p.snr is not None:
                    snr[center].append(p.snr)
                if p.fwhm is not None:
                    fwhm[center].append(p.fwhm)
    med = lambda xs: statistics.median(xs) if xs else float("nan")  # noqa: E731
    return {
        "noise": med(noise),
        "snr": {c: med(v) for c, v in snr.items()},
        "fwhm": {c: med(v) for c, v in fwhm.items()},
        "found": {c: len(v) for c, v in snr.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pixel-noise", type=float, default=3.0, help="per-pixel noise sigma, counts")
    ap.add_argument("--baseline", type=float, default=10.0, help="dark level, counts")
    ap.add_argument("--slit-rows", type=int, default=401, help="height of the slit image, rows")
    ap.add_argument("--tilt", type=float, default=0.005, help="slit tilt for the tilted run, px/row")
    ap.add_argument("--frames", type=int, default=15, help="frames per setting")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--heights", default="1,3,9,25,81,201,401")
    args = ap.parse_args()
    heights = [int(h) for h in args.heights.split(",")]
    dim = LINES[1][0]

    print(f"Simulated 1280x800 8-bit frames: per-pixel noise {args.pixel_noise} counts, "
          f"slit image {args.slit_rows} rows, {args.frames} frames per setting.")
    print(f"Lines (px, counts, FWHM px): {LINES}; SNR shown for the dim line at {dim} px.\n")

    for tilt in (0.0, args.tilt):
        print(f"Tilt {tilt} px/row ({tilt * (args.slit_rows - 1):.1f} px end to end across the slit image)")
        print("| rows | noise (float) | SNR (float) | SNR gain vs 3 rows | SNR (integer) | FWHM px (float) |")
        print("|-----:|--------------:|------------:|-------------------:|--------------:|----------------:|")
        ref = None
        for h in heights:
            f = measure(h, "float", tilt, args)
            i = measure(h, "integer", tilt, args)
            if h == 3:
                ref = f["snr"][dim]
            gain = f["snr"][dim] / ref if ref else float("nan")
            print(f"| {h:>4} | {f['noise']:13.3f} | {f['snr'][dim]:11.1f} | "
                  f"{(f'{gain:.2f}x' if ref else '-'):>18} | {i['snr'][dim]:13.1f} | "
                  f"{f['fwhm'][dim]:15.2f} |")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
