"""Wavelength graticule marks for calibrated displays (Qt-free, plot-free).

A port of the original PySpectrometer2 ``specFunctions.generateGraticule``:
given a per-pixel wavelength axis, find the *pixel* position of every whole
10 nm and 50 nm. The spectrum and waterfall views draw their nm scale from this.

Why pixel positions rather than a linear nm axis: the calibration is a 2nd/3rd
order polynomial, so nm is not linear in pixel. Stretching an image across a
min..max nm range would misplace every line between the endpoints by an amount
that grows with the fit's curvature. Locating each mark on the real axis keeps
the scale honest whatever the fit order.

Kept free of Qt and matplotlib imports so it is unit tested without a display
and can be shared by the live widget and the PNG renderer.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

# The original's constants: look 10 nm beyond each end of the axis for candidate
# marks, and keep a mark only where some pixel lands within 1 nm of it. The
# tolerance is what stops a compressed axis from stacking dozens of labels at
# the ends.
_MARGIN_NM = 10
_TOLERANCE_NM = 1.0

Mark = Tuple[int, int]  # (pixel index, label in nm)


def marks(wavelengths: Sequence[float], step_nm: int = 50,
          tolerance_nm: float = _TOLERANCE_NM) -> List[Mark]:
    """Pixel positions of every whole ``step_nm`` on a calibrated axis.

    Returns ``[(pixel_index, wavelength_nm), ...]`` in ascending pixel order.
    A mark is emitted only where some pixel falls within ``tolerance_nm`` of the
    target, so an axis that does not actually reach a round number does not get
    a label pinned to its edge.

    Returns ``[]`` for a missing or too-short axis: an uncalibrated display has
    no wavelength scale to draw and must fall back to pixel labels rather than
    invent one.
    """
    if wavelengths is None or len(wavelengths) < 2 or step_nm <= 0:
        return []

    axis = [float(w) for w in wavelengths]
    # The original indexed [0] and [-1] directly, assuming an ascending axis.
    # min/max is identical in that case and stays correct if a grating/sensor
    # orientation puts long wavelengths at low pixel numbers.
    first, last = axis[0], axis[-1]
    low = int(round(min(first, last))) - _MARGIN_NM
    high = int(round(max(first, last))) + _MARGIN_NM

    found: List[Mark] = []
    for target in range(low, high):
        if target % step_nm:
            continue
        index = min(range(len(axis)), key=lambda i: abs(target - axis[i]))
        if abs(target - axis[index]) < tolerance_nm:
            # Label with the wavelength actually at that pixel (as the original
            # did) rather than the target: inside the 1 nm tolerance they agree,
            # and this reports what the calibration says, not what was asked.
            found.append((index, int(round(axis[index]))))
    return found


def tens_and_fifties(wavelengths: Sequence[float]) -> Tuple[List[int], List[Mark]]:
    """``(tens, fifties)`` - minor tick pixels and labelled major marks.

    Mirrors the original ``generateGraticule`` return shape: bare pixel indices
    for the 10 nm minor ticks, ``(pixel, nm)`` pairs for the labelled 50 nm ones.
    """
    tens = [pixel for pixel, _nm in marks(wavelengths, 10)]
    fifties = marks(wavelengths, 50)
    return tens, fifties
