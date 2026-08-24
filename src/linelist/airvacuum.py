"""Air <-> vacuum wavelength conversion.

NIST ASD reports wavelengths above 200 nm in **standard air** by default and in
vacuum below it, so any line list carries a convention that must travel with the
numbers. Mixing the two is a ~0.22 nm error at 810 nm — the same order as this
instrument's best-case resolution, and therefore a silent-bad-data class of
failure rather than a rounding detail.

The refractive index of standard air (15 degC, 101.325 kPa, 0.045% CO2) follows
Peck & Reeder (1972), *J. Opt. Soc. Am.* **62**, 958, which is the formula ASD
itself uses. Matching ASD's own choice matters: the Edlen (1953) and Ciddor
(1996) formulations differ from it by ~1e-8 in n, which is negligible here, but
using the same reference removes the question entirely.

Peck & Reeder is expressed as n(lambda_vacuum), so vacuum -> air is direct and
air -> vacuum is solved by fixed-point iteration (it converges in two passes;
the loop is bounded regardless).
"""

from __future__ import annotations

_MAX_ITER = 8
_TOLERANCE_NM = 1e-9


def refractive_index(wavelength_vacuum_nm: float) -> float:
    """Refractive index of standard air at a **vacuum** wavelength, in nm.

    Peck & Reeder (1972), with sigma the vacuum wavenumber in inverse microns.
    """
    if wavelength_vacuum_nm <= 0:
        raise ValueError("wavelength must be positive")
    sigma_sq = (1.0e3 / wavelength_vacuum_nm) ** 2      # nm -> um, then squared
    n_minus_1 = (
        8060.51
        + 2_480_990.0 / (132.274 - sigma_sq)
        + 17_455.7 / (39.32957 - sigma_sq)
    ) * 1.0e-8
    return 1.0 + n_minus_1


def vacuum_to_air(wavelength_vacuum_nm: float) -> float:
    """Convert a vacuum wavelength (nm) to standard air."""
    return wavelength_vacuum_nm / refractive_index(wavelength_vacuum_nm)


def air_to_vacuum(wavelength_air_nm: float) -> float:
    """Convert a standard-air wavelength (nm) to vacuum.

    Fixed-point iteration on ``lambda_vac = lambda_air * n(lambda_vac)``. The
    first guess (lambda_air) is already within ~0.2 nm, so this converges to
    below 1e-9 nm in two iterations; the bound exists only to make the loop
    total.
    """
    if wavelength_air_nm <= 0:
        raise ValueError("wavelength must be positive")
    guess = wavelength_air_nm
    for _ in range(_MAX_ITER):
        updated = wavelength_air_nm * refractive_index(guess)
        if abs(updated - guess) < _TOLERANCE_NM:
            return updated
        guess = updated
    return guess
