"""Slit width from laser diffraction (SLIT-001..004) against the simulator (SYN-010)."""

import json
import math
from dataclasses import replace

import numpy as np
import pytest

from calibration.slit import (
    fit_dial_calibration, fit_dial_calibration_from_results, fringe_positions_mm,
    measure_slit_width,
)
from errors import CalibrationError
from synthetic.diffraction import (
    DiffractionSpec, simulate_dial_series, simulate_marks, wall_profile,
)

EXACT = DiffractionSpec(mark_sigma_mm=0.0)


def _fit(spec, **kw):
    orders, pos = simulate_marks(spec)
    return measure_slit_width(orders, pos, spec.wavelength_nm, spec.distance_mm, **kw)


# --- geometry ---------------------------------------------------------------

def test_first_fringe_hand_value():
    # 12.7 um, 650 nm, 2 m: sin(theta) = 0.0511811, y = L tan(theta) = 102.4965 mm
    # (the small-angle shortcut would say 102.3622)
    y = fringe_positions_mm(12.7, 650.0, 2000.0, [1])[0]
    assert y == pytest.approx(102.4965, abs=1e-3)


def test_fringe_positions_match_simulator():
    orders, pos = simulate_marks(EXACT)
    ours = fringe_positions_mm(12.7, 650.0, 2000.0, orders, center_mm=500.0)
    assert ours == pytest.approx(pos, abs=1e-9)


def test_wall_profile_is_dark_at_fringes_and_bright_at_center():
    orders, pos = simulate_marks(EXACT)
    assert np.max(wall_profile(EXACT, pos)) < 1e-20
    assert wall_profile(EXACT, [EXACT.center_mm])[0] == pytest.approx(1.0)


def test_missing_order_raises():
    with pytest.raises(CalibrationError):
        fringe_positions_mm(12.7, 650.0, 2000.0, [20])


# --- single setting ---------------------------------------------------------

def test_noise_free_recovers_width_and_center_exactly():
    r = _fit(EXACT, mark_sigma_mm=None)
    assert r.width_um == pytest.approx(12.7, abs=1e-9)
    assert r.center_mm == pytest.approx(500.0, abs=1e-9)
    assert r.direction == 1
    assert r.rms_residual_mm < 1e-9


def test_small_angle_shortcut_is_biased_exact_fit_is_not():
    r = _fit(EXACT, mark_sigma_mm=None)
    assert abs(r.small_angle_width_um - 12.7) / 12.7 > 0.005
    assert r.width_um == pytest.approx(12.7, rel=1e-10)


@pytest.mark.parametrize("seed", range(5))
def test_typical_bench_session_is_well_inside_one_micron(seed):
    r = _fit(replace(DiffractionSpec(), seed=seed))
    assert abs(r.width_um - 12.7) < 3 * r.sigma_um
    assert r.sigma_um < 0.2


@pytest.mark.parametrize("center,direction", [(0.0, 1), (1234.5, -1), (-80.0, -1)])
def test_tape_zero_and_direction_do_not_matter(center, direction):
    r = _fit(replace(EXACT, center_mm=center, direction=direction), mark_sigma_mm=None)
    assert r.width_um == pytest.approx(12.7, rel=1e-9)
    assert r.center_mm == pytest.approx(center, abs=1e-6)
    assert r.direction == direction


def test_marks_on_one_side_only():
    r = _fit(replace(EXACT, orders=(1, 2, 3, 4, 5)), mark_sigma_mm=None)
    assert r.width_um == pytest.approx(12.7, rel=1e-9)


@pytest.mark.parametrize("width", [10.0, 25.0, 50.0, 100.0, 250.0])
def test_other_widths(width):
    spec = replace(DiffractionSpec(), width_um=width, seed=3)
    r = _fit(spec)
    assert abs(r.width_um - width) < 3 * r.sigma_um


def test_width_scales_exactly_with_wavelength():
    orders, pos = simulate_marks(DiffractionSpec(seed=1))
    a = measure_slit_width(orders, pos, 650.0, 2000.0).width_um
    b = measure_slit_width(orders, pos, 656.5, 2000.0).width_um
    assert b / a == pytest.approx(1.01, rel=1e-9)


def test_uncertainty_terms():
    r = _fit(DiffractionSpec(seed=2), wavelength_sigma_nm=0.5, distance_sigma_mm=2.0)
    assert r.sigma_wavelength_um == pytest.approx(r.width_um * 0.5 / 650.0, rel=1e-9)
    # d(ln a)/d(ln L) = cos^2(theta) per mark, so a little under proportional:
    # ~0.97 with orders out to +-4 (theta up to 11.8 degrees).
    ratio = r.sigma_distance_um / (r.width_um * 2.0 / 2000.0)
    assert 0.94 < ratio < 1.0
    assert r.sigma_um == pytest.approx(math.sqrt(
        r.sigma_stat_um ** 2 + r.sigma_wavelength_um ** 2 + r.sigma_distance_um ** 2))


def test_mark_sigma_is_a_floor():
    r = _fit(EXACT, mark_sigma_mm=1.5)
    assert r.mark_sigma_mm == 1.5
    assert r.sigma_stat_um > 0


def test_statistical_sigma_is_honest():
    """Scatter-only sigma from 8 marks (6 dof): P(|t| < 1) = 0.64."""
    hits = 0
    for seed in range(300):
        r = _fit(replace(DiffractionSpec(), seed=seed, mark_sigma_mm=2.0), mark_sigma_mm=None)
        hits += abs(r.width_um - 12.7) <= r.sigma_stat_um
    assert 0.56 <= hits / 300 <= 0.72


@pytest.mark.parametrize("orders,pos,lam,L", [
    ([1, 2], [100.0, 200.0], 650.0, 2000.0),             # too few marks
    ([1, 0, 2], [100.0, 0.0, 200.0], 650.0, 2000.0),     # order 0
    ([1, 1.5, 2], [100.0, 150.0, 200.0], 650.0, 2000.0),  # non-integer
    ([1, 1, 1], [100.0, 101.0, 99.0], 650.0, 2000.0),    # one distinct order
    ([1, 2, 3], [100.0, 200.0], 650.0, 2000.0),          # length mismatch
    ([1, 2, 3], [100.0, 200.0, 300.0], 0.0, 2000.0),     # bad wavelength
    ([1, 2, 3], [100.0, 200.0, 300.0], 650.0, -1.0),     # bad distance
    ([1, 2, 3], [100.0, 100.0, 100.0], 650.0, 2000.0),   # no change with order
])
def test_bad_input_raises(orders, pos, lam, L):
    with pytest.raises(CalibrationError):
        measure_slit_width(orders, pos, lam, L)


def test_result_is_json_serializable():
    json.dumps(_fit(DiffractionSpec()).as_dict())


# --- variable slit: dial calibration ----------------------------------------

def test_dial_fit_noise_free():
    dials = [10.0, 20.0, 40.0, 70.0, 100.0]
    widths = [0.98 * (d - 3.0) for d in dials]       # screw 2 % short, zero at 3
    cal = fit_dial_calibration(dials, widths)
    assert cal.scale_um_per_unit == pytest.approx(0.98)
    assert cal.zero_dial == pytest.approx(3.0)
    assert cal.width_at(50.0)[0] == pytest.approx(0.98 * 47.0)


def test_dial_session_end_to_end():
    dials = [10.0, 20.0, 40.0, 70.0, 100.0]
    base = DiffractionSpec(seed=11)
    results = []
    for dial, orders, pos in simulate_dial_series(1.02, 2.5, dials, base):
        results.append(measure_slit_width(orders, pos, base.wavelength_nm,
                                          base.distance_mm))
    cal = fit_dial_calibration_from_results(dials, results)
    assert abs(cal.zero_dial - 2.5) < 3 * cal.sigma_zero_dial
    assert abs(cal.scale_um_per_unit - 1.02) < 3 * cal.sigma_scale
    assert cal.sigma_zero_dial < 0.5
    w, s = cal.width_at(30.0)
    assert abs(w - 1.02 * 27.5) < 3 * s


def test_dial_reading_below_zero_refuses():
    cal = fit_dial_calibration([10.0, 20.0, 30.0], [7.0, 17.0, 27.0])
    with pytest.raises(CalibrationError):
        cal.width_at(2.0)


def test_dial_weighted_needs_two_unweighted_needs_three():
    fit_dial_calibration([10.0, 20.0], [7.0, 17.0], sigmas_um=[0.1, 0.1])
    with pytest.raises(CalibrationError):
        fit_dial_calibration([10.0, 20.0], [7.0, 17.0])
    with pytest.raises(CalibrationError):
        fit_dial_calibration([10.0, 10.0, 10.0], [7.0, 7.1, 6.9])


def test_dial_scatter_inflates_weighted_sigma():
    dials, widths = [10.0, 20.0, 30.0, 40.0], [7.0, 18.0, 26.0, 37.5]
    tight = fit_dial_calibration(dials, widths, sigmas_um=[0.01] * 4)
    assert tight.sigma_zero_dial > 0.1      # chi-square inflation kicked in


def test_dial_calibration_is_json_serializable():
    json.dumps(fit_dial_calibration([10.0, 20.0, 30.0], [7.0, 17.1, 26.9]).as_dict())
