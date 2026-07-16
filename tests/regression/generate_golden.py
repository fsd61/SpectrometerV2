"""Regenerate the golden fixtures by running the BASELINE functions.

Run from the repo root:  PYTHONPATH=tests python tests/regression/generate_golden.py

This is intentionally separate from the tests: it captures the baseline's
current outputs into tests/regression/golden/*.json. The regression tests then
re-run the baseline and assert equivalence to these snapshots (and, later, the
migrated modules will be checked against the same snapshots).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile

import numpy as np

from regression import _baseline as B

SAVGOL_WINDOW = 17
SAVGOL_ORDER = 3
PEAK_THRES = 0.2
PEAK_MIN_DIST = 20
RGB_SAMPLES = [300, 380, 405, 436, 470, 510, 546, 589, 611, 650, 700, 750, 800]
SAMPLE_PIXELS = [0, 100, 200, 300, 400, 500, 600, 700, 799]


def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def main():
    sf = B.load_baseline()
    B.GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    x, y = B.reference_spectrum()

    # 1. Savitzky-Golay smoothing
    smoothed = np.asarray(_quiet(sf.savitzky_golay, y, SAVGOL_WINDOW, SAVGOL_ORDER), dtype=float)
    _dump("savgol.json", {
        "window": SAVGOL_WINDOW, "order": SAVGOL_ORDER,
        "input": {"width": B.REFERENCE_WIDTH, "lines": B.REFERENCE_LINES,
                  "baseline": B.REFERENCE_BASELINE, "noise": B.REFERENCE_NOISE,
                  "seed": B.REFERENCE_SEED},
        "output": [round(float(v), 8) for v in smoothed],
    })

    # 2. Peak detection (on the smoothed reference)
    peaks = _quiet(sf.peakIndexes, smoothed, thres=PEAK_THRES, min_dist=PEAK_MIN_DIST)
    _dump("peaks.json", {
        "thres": PEAK_THRES, "min_dist": PEAK_MIN_DIST,
        "indices": [int(i) for i in np.asarray(peaks)],
    })

    # 3. wavelength_to_rgb
    _dump("wavelength_to_rgb.json", {
        "map": [[nm, list(map(int, sf.wavelength_to_rgb(nm)))] for nm in RGB_SAMPLES],
    })

    # 4. Calibration (readcal) for both the 4-point and 3-point cases
    cal_records = {}
    for tag, px, wl in [("multi", B.CAL_PIXELS, B.CAL_WAVELENGTHS),
                        ("three", B.CAL3_PIXELS, B.CAL3_WAVELENGTHS)]:
        with tempfile.TemporaryDirectory() as d:
            B.write_caldata(d, px, wl)
            cwd = os.getcwd(); os.chdir(d)
            try:
                cal = _quiet(sf.readcal, B.REFERENCE_WIDTH)
            finally:
                os.chdir(cwd)
        wldata = cal[0]
        cal_records[tag] = {
            "pixels": px, "wavelengths": wl,
            "messages": [cal[1], cal[2], cal[3]],
            "length": len(wldata),
            "sampled": {str(p): round(float(wldata[p]), 6) for p in SAMPLE_PIXELS},
        }
        if tag == "multi":
            graticule = _quiet(sf.generateGraticule, wldata)
    _dump("calibration.json", cal_records)

    # 5. Graticule (from the multi-point calibration)
    _dump("graticule.json", {
        "tens": [int(i) for i in graticule[0]],
        "fifties": [[int(p), int(lbl)] for p, lbl in graticule[1]],
    })

    print("Golden fixtures written to", B.GOLDEN_DIR)


def _dump(name, obj):
    (B.GOLDEN_DIR / name).write_text(json.dumps(obj, indent=1), encoding="utf-8")
    print("  wrote", name)


if __name__ == "__main__":
    main()
