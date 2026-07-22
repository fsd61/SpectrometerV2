"""Phase 3 equivalence: the extracted src/ modules reproduce the golden fixtures.

This is the provable-equivalence check for Gate C — the migrated scientific
functions must match the baseline's golden outputs before the legacy paths are
retired.
"""

import json

import numpy as np
import pytest

from . import _baseline as B

from analysis.smoothing import savitzky_golay          # noqa: E402 (src on pythonpath)
from analysis.peaks import peak_indexes                 # noqa: E402
from calibration.wavelength import calibrate            # noqa: E402


def _golden(name):
    return json.loads((B.GOLDEN_DIR / name).read_text(encoding="utf-8"))


def test_savgol_equivalent_to_golden():
    g = _golden("savgol.json")
    _, y = B.reference_spectrum()
    out = savitzky_golay(y, g["window"], g["order"])
    assert np.allclose(out, np.asarray(g["output"]), atol=1e-6)


def test_peaks_equivalent_to_golden():
    g = _golden("savgol.json")
    gp = _golden("peaks.json")
    _, y = B.reference_spectrum()
    out = savitzky_golay(y, g["window"], g["order"])
    peaks = [int(i) for i in peak_indexes(out, thres=gp["thres"], min_dist=gp["min_dist"])]
    assert peaks == gp["indices"]


def test_calibration_equivalent_to_golden():
    gc = _golden("calibration.json")
    cases = {"multi": (B.CAL_PIXELS, B.CAL_WAVELENGTHS),
             "three": (B.CAL3_PIXELS, B.CAL3_WAVELENGTHS)}
    order_to_msg = {2: "2nd Order Polyfit", 3: "3rd Order Polyfit"}
    for tag, (pixels, wavelengths) in cases.items():
        rec = gc[tag]
        res = calibrate(pixels, wavelengths, rec["length"])
        assert len(res.wavelengths) == rec["length"]
        for pixel, expected in rec["sampled"].items():
            assert res.wavelengths[int(pixel)] == pytest.approx(expected, abs=1e-6)
        # order must agree with the baseline's recorded polynomial message
        assert order_to_msg[res.order] == rec["messages"][2]
