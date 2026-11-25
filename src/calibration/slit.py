"""Slit width from single-slit laser diffraction (SLIT-001..SLIT-004).

A collimated laser through the entrance slit throws a single-slit (Fraunhofer)
pattern on a wall. Dark fringes sit where

    a * sin(theta_m) = m * lambda,        m = +-1, +-2, ...

On a flat wall at perpendicular distance L, fringe m lands at

    y_m = y0 + L * tan(asin(m * lambda / a))

where y0 is the pattern center as read on the user's tape. The fit solves for
the width a and the center y0 together from every marked fringe, so the user
never has to locate the middle of the bright spot, and marks may start from
any zero on the tape. The exact geometry is used throughout: the small-angle
shortcut y = m*lambda*L/a is already ~1 % off by the 3rd order for a 12.7 um
slit at 650 nm.

The fitted width scales exactly with the laser wavelength (y depends only on
lambda/a), so the wavelength should be measured with the spectrometer itself;
a nominal "650 nm" label is otherwise the largest error in the budget.

For a variable slit, :func:`fit_dial_calibration` fits measured width against
micrometer reading, giving the true mechanical zero and the screw scale.

Units at the API: wavelength in nm, distance and tape positions in mm, widths
in um. Dial readings are in whatever unit the micrometer shows.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional, Sequence

import numpy as np

from errors import CalibrationError

METHOD_ID = "laser-single-slit-v1"
DIAL_METHOD_ID = "dial-linear-v1"
DEFAULT_MARK_SIGMA_MM = 1.0     # pencil mark on a dark-fringe center, typical
_MAX_ITER = 100


# --------------------------------------------------------------------------
# Single setting: width from marked dark fringes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SlitWidthResult:
    """Width of one slit setting from one set of fringe marks."""

    width_um: float
    sigma_um: float                 # total: stat, wavelength, distance in quadrature
    sigma_stat_um: float            # from mark scatter (or the mark-sigma floor)
    sigma_wavelength_um: float
    sigma_distance_um: float
    center_mm: float                # fitted pattern center on the tape
    direction: int                  # +1 if tape reading grows toward +orders
    rms_residual_mm: float
    residuals_mm: tuple
    orders: tuple
    positions_mm: tuple
    wavelength_nm: float
    wavelength_sigma_nm: float
    distance_mm: float
    distance_sigma_mm: float
    mark_sigma_mm: float            # per-mark sigma actually used for sigma_stat
    small_angle_width_um: float     # the shortcut's answer, for comparison only
    method: str = METHOD_ID

    def as_dict(self) -> dict:
        d = asdict(self)
        for key in ("residuals_mm", "orders", "positions_mm"):
            d[key] = list(d[key])
        return d


def fringe_positions_mm(width_um: float, wavelength_nm: float, distance_mm: float,
                        orders: Sequence[int], center_mm: float = 0.0,
                        direction: int = 1) -> list[float]:
    """Where dark fringe ``m`` lands on the wall (exact geometry).

    Useful for telling the user where to look before they start marking.
    Raises :class:`CalibrationError` for an order that does not exist
    (|m| * lambda >= a).
    """
    a = width_um * 1e-3
    lam = wavelength_nm * 1e-6
    out = []
    for m in orders:
        u = m * lam / a
        if abs(u) >= 1.0:
            raise CalibrationError(
                f"order {m} does not exist for a {width_um:g} um slit at {wavelength_nm:g} nm")
        out.append(center_mm + direction * distance_mm * u / math.sqrt(1.0 - u * u))
    return out


def _residuals(md, y, a, y0, lam, L):
    u = md * lam / a
    if a <= 0 or np.any(np.abs(u) >= 1.0):
        return None
    return y - (y0 + L * u / np.sqrt(1.0 - u * u))


def _jacobian(md, a, lam, L):
    """d(model)/d(a, y0)."""
    u = md * lam / a
    return np.column_stack([-L * u / (a * (1.0 - u * u) ** 1.5), np.ones_like(u)])


def _solve(m, y, lam, L):
    """Gauss-Newton fit of (a, y0). All lengths in mm.

    Returns (a, y0, residuals, jacobian, direction, small_angle_a).
    """
    A = np.column_stack([m, np.ones_like(m)])
    (slope, intercept), *_ = np.linalg.lstsq(A, y, rcond=None)
    span = abs(slope) * float(np.ptp(m))
    if not np.isfinite(slope) or span <= 1e-9 * max(1.0, float(np.max(np.abs(y)))):
        raise CalibrationError("fringe positions do not change with order")
    direction = 1 if slope > 0 else -1
    md = m * direction
    small_angle_a = lam * L / abs(slope)

    # Start from the small-angle answer, nudged so every marked order exists.
    a = max(small_angle_a, 1.05 * float(np.max(np.abs(m))) * lam)
    y0 = float(intercept)
    r = _residuals(md, y, a, y0, lam, L)
    cost = float(r @ r)

    for _ in range(_MAX_ITER):
        delta, *_ = np.linalg.lstsq(_jacobian(md, a, lam, L), r, rcond=None)
        step, accepted = 1.0, False
        while step > 1e-8:
            a_new, y0_new = a + step * delta[0], y0 + step * delta[1]
            r_new = _residuals(md, y, a_new, y0_new, lam, L)
            if r_new is not None and float(r_new @ r_new) <= cost:
                accepted = True
                break
            step *= 0.5
        if not accepted:
            break
        moved = abs(a_new - a)
        a, y0, r, cost = a_new, y0_new, r_new, float(r_new @ r_new)
        if moved <= 1e-13 * a:
            break

    return a, y0, r, _jacobian(md, a, lam, L), direction, small_angle_a


def measure_slit_width(orders: Sequence[int], positions_mm: Sequence[float],
                       wavelength_nm: float, distance_mm: float, *,
                       mark_sigma_mm: Optional[float] = DEFAULT_MARK_SIGMA_MM,
                       wavelength_sigma_nm: float = 0.0,
                       distance_sigma_mm: float = 0.0) -> SlitWidthResult:
    """Fit the slit width to marked dark-fringe positions.

    ``orders`` are the signed fringe numbers (+-1, +-2, ...; never 0) and
    ``positions_mm`` the tape readings of their centers, from any zero.
    Which side is "+" does not matter; the fit detects the direction.

    ``mark_sigma_mm`` is a floor on the per-mark uncertainty: the statistical
    sigma uses the larger of it and the observed scatter, so three marks that
    happen to line up perfectly cannot claim zero error. Pass ``None`` to use
    the scatter alone (needs at least 3 marks).
    """
    m = np.asarray(orders, dtype=float)
    y = np.asarray(positions_mm, dtype=float)
    if m.shape != y.shape or m.ndim != 1:
        raise CalibrationError("orders and positions must be equal-length lists")
    if len(m) < 3:
        raise CalibrationError("mark at least 3 dark fringes")
    if np.any(m != np.round(m)) or np.any(m == 0):
        raise CalibrationError("orders must be nonzero integers (+-1, +-2, ...)")
    if len(set(m.tolist())) < 2:
        raise CalibrationError("mark at least 2 different orders")
    if not np.all(np.isfinite(y)):
        raise CalibrationError("positions must be finite numbers")
    if not wavelength_nm > 0 or not distance_mm > 0:
        raise CalibrationError("wavelength and distance must be positive")
    if wavelength_sigma_nm < 0 or distance_sigma_mm < 0:
        raise CalibrationError("uncertainties cannot be negative")
    if mark_sigma_mm is not None and mark_sigma_mm < 0:
        raise CalibrationError("mark sigma cannot be negative")

    lam = wavelength_nm * 1e-6
    L = float(distance_mm)
    a, y0, r, J, direction, small_a = _solve(m, y, lam, L)

    dof = len(m) - 2
    scatter = math.sqrt(float(r @ r) / dof)
    sigma_y = scatter if mark_sigma_mm is None else max(scatter, float(mark_sigma_mm))
    cov = sigma_y ** 2 * np.linalg.inv(J.T @ J)
    sigma_stat = math.sqrt(max(float(cov[0, 0]), 0.0))

    # a scales exactly with lambda.
    sigma_lam = a * wavelength_sigma_nm / wavelength_nm
    # Distance: numerical derivative of the refit.
    h = 1e-3 * L
    a_plus = _solve(m, y, lam, L + h)[0]
    a_minus = _solve(m, y, lam, L - h)[0]
    sigma_L = abs((a_plus - a_minus) / (2 * h)) * distance_sigma_mm

    total = math.sqrt(sigma_stat ** 2 + sigma_lam ** 2 + sigma_L ** 2)
    return SlitWidthResult(
        width_um=a * 1e3, sigma_um=total * 1e3, sigma_stat_um=sigma_stat * 1e3,
        sigma_wavelength_um=sigma_lam * 1e3, sigma_distance_um=sigma_L * 1e3,
        center_mm=float(y0), direction=direction,
        rms_residual_mm=math.sqrt(float(r @ r) / len(m)),
        residuals_mm=tuple(float(v) for v in r),
        orders=tuple(int(v) for v in m), positions_mm=tuple(float(v) for v in y),
        wavelength_nm=float(wavelength_nm), wavelength_sigma_nm=float(wavelength_sigma_nm),
        distance_mm=L, distance_sigma_mm=float(distance_sigma_mm),
        mark_sigma_mm=sigma_y, small_angle_width_um=small_a * 1e3,
    )


# --------------------------------------------------------------------------
# Variable slit: width vs micrometer reading
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DialCalibration:
    """Linear map from micrometer reading to true slit width.

    width_um = scale_um_per_unit * dial + offset_um. ``zero_dial`` is the
    reading at which the jaws actually close (the mechanical zero), which is
    rarely where the dial says 0.
    """

    scale_um_per_unit: float
    offset_um: float
    zero_dial: float
    sigma_scale: float
    sigma_offset_um: float
    sigma_zero_dial: float
    rms_residual_um: float
    residuals_um: tuple
    dial_readings: tuple
    widths_um: tuple
    sigmas_um: tuple            # empty when the fit was unweighted
    covariance: tuple           # ((var_s, cov), (cov, var_c))
    method: str = DIAL_METHOD_ID

    def width_at(self, dial: float) -> tuple[float, float]:
        """(width_um, sigma_um) at a dial reading; refuses at/below zero."""
        w = self.scale_um_per_unit * dial + self.offset_um
        if w <= 0.0:
            raise CalibrationError(
                f"dial {dial:g} is at or below the mechanical zero ({self.zero_dial:.3f})")
        cov = np.asarray(self.covariance)
        g = np.array([dial, 1.0])
        return w, math.sqrt(max(float(g @ cov @ g), 0.0))

    def as_dict(self) -> dict:
        d = asdict(self)
        for key in ("residuals_um", "dial_readings", "widths_um", "sigmas_um"):
            d[key] = list(d[key])
        d["covariance"] = [list(row) for row in d["covariance"]]
        return d


def fit_dial_calibration(dial_readings: Sequence[float], widths_um: Sequence[float],
                         sigmas_um: Optional[Sequence[float]] = None) -> DialCalibration:
    """Fit true width against micrometer reading for a variable slit.

    With ``sigmas_um`` (e.g. each :attr:`SlitWidthResult.sigma_um`) the fit is
    weighted and needs 2+ distinct readings; the covariance is inflated by the
    reduced chi-square when the points scatter more than their sigmas claim.
    Without sigmas the fit is unweighted and needs 3+ readings so the scatter
    can be measured.
    """
    d = np.asarray(dial_readings, dtype=float)
    w = np.asarray(widths_um, dtype=float)
    if d.shape != w.shape or d.ndim != 1:
        raise CalibrationError("dial readings and widths must be equal-length lists")
    if not (np.all(np.isfinite(d)) and np.all(np.isfinite(w))):
        raise CalibrationError("dial readings and widths must be finite numbers")
    if len(set(d.tolist())) < 2:
        raise CalibrationError("measure at least 2 different dial settings")

    X = np.column_stack([d, np.ones_like(d)])
    n = len(d)
    if sigmas_um is not None:
        s = np.asarray(sigmas_um, dtype=float)
        if s.shape != d.shape or np.any(s <= 0) or not np.all(np.isfinite(s)):
            raise CalibrationError("sigmas must be positive, one per setting")
        W = 1.0 / s ** 2
        cov = np.linalg.inv(X.T @ (X * W[:, None]))
        params = cov @ (X.T @ (W * w))
        r = w - X @ params
        if n > 2:
            chi2_red = float(np.sum(W * r ** 2)) / (n - 2)
            cov = cov * max(1.0, chi2_red)
        sig_tuple = tuple(float(v) for v in s)
    else:
        if n < 3:
            raise CalibrationError("unweighted fit needs at least 3 settings (or pass sigmas)")
        params, *_ = np.linalg.lstsq(X, w, rcond=None)
        r = w - X @ params
        cov = float(r @ r) / (n - 2) * np.linalg.inv(X.T @ X)
        sig_tuple = ()

    scale, offset = float(params[0]), float(params[1])
    if scale <= 0.0:
        raise CalibrationError("width does not increase with dial reading")
    zero = -offset / scale
    g = np.array([offset / scale ** 2, -1.0 / scale])     # d(zero)/d(scale, offset)
    return DialCalibration(
        scale_um_per_unit=scale, offset_um=offset, zero_dial=zero,
        sigma_scale=math.sqrt(max(float(cov[0, 0]), 0.0)),
        sigma_offset_um=math.sqrt(max(float(cov[1, 1]), 0.0)),
        sigma_zero_dial=math.sqrt(max(float(g @ cov @ g), 0.0)),
        rms_residual_um=math.sqrt(float(r @ r) / n),
        residuals_um=tuple(float(v) for v in r),
        dial_readings=tuple(float(v) for v in d), widths_um=tuple(float(v) for v in w),
        sigmas_um=sig_tuple,
        covariance=tuple(tuple(float(v) for v in row) for row in cov),
    )


def fit_dial_calibration_from_results(dial_readings: Sequence[float],
                                      results: Sequence[SlitWidthResult]) -> DialCalibration:
    """Convenience: dial fit straight from per-setting laser measurements."""
    return fit_dial_calibration(dial_readings, [r.width_um for r in results],
                                [r.sigma_um for r in results])
