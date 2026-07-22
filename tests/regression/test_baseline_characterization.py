"""Golden characterization tests (Migration Plan Phase 1).

These PIN the proven outputs of Les Wright's baseline ``specFunctions.py`` so
that the migrated scientific core can later be checked against the very same
golden fixtures and proven numerically equivalent. Regenerate fixtures with:

    PYTHONPATH=tests python tests/regression/generate_golden.py
"""

import json
import os

import numpy as np
import pytest

from . import _baseline as B

SAVGOL_ATOL = 1e-6
CAL_ATOL = 1e-6


@pytest.fixture(scope="module")
def baseline():
    return B.load_baseline()


def _golden(name):
    return json.loads((B.GOLDEN_DIR / name).read_text(encoding="utf-8"))


def test_savgol_matches_golden(baseline):
    g = _golden("savgol.json")
    _, y = B.reference_spectrum()
    out = np.asarray(baseline.savitzky_golay(y, g["window"], g["order"]), dtype=float)
    expected = np.asarray(g["output"], dtype=float)
    assert out.shape == expected.shape
    assert np.allclose(out, expected, atol=SAVGOL_ATOL), \
        f"max abs diff = {np.max(np.abs(out - expected))}"


def test_peaks_match_golden(baseline):
    g = _golden("peaks.json")
    _, y = B.reference_spectrum()
    smoothed = np.asarray(baseline.savitzky_golay(y, 17, 3), dtype=float)
    peaks = [int(i) for i in np.asarray(
        baseline.peakIndexes(smoothed, thres=g["thres"], min_dist=g["min_dist"]))]
    assert peaks == g["indices"]


def test_wavelength_to_rgb_matches_golden(baseline):
    for nm, rgb in _golden("wavelength_to_rgb.json")["map"]:
        assert list(map(int, baseline.wavelength_to_rgb(nm))) == rgb, f"nm={nm}"


def test_calibration_matches_golden(baseline, tmp_path):
    g = _golden("calibration.json")
    for tag in ("multi", "three"):
        rec = g[tag]
        d = tmp_path / tag
        d.mkdir()
        B.write_caldata(d, rec["pixels"], rec["wavelengths"])
        cwd = os.getcwd()
        os.chdir(d)
        try:
            cal = baseline.readcal(rec["length"])
        finally:
            os.chdir(cwd)
        assert [cal[1], cal[2], cal[3]] == rec["messages"]
        assert len(cal[0]) == rec["length"]
        for pixel, expected in rec["sampled"].items():
            assert cal[0][int(pixel)] == pytest.approx(expected, abs=CAL_ATOL)


def test_graticule_matches_golden(baseline, tmp_path):
    g = _golden("graticule.json")
    cal_multi = _golden("calibration.json")["multi"]
    B.write_caldata(tmp_path, cal_multi["pixels"], cal_multi["wavelengths"])
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cal = baseline.readcal(cal_multi["length"])
    finally:
        os.chdir(cwd)
    graticule = baseline.generateGraticule(cal[0])
    assert [int(i) for i in graticule[0]] == g["tens"]
    assert [[int(p), int(lbl)] for p, lbl in graticule[1]] == g["fifties"]
