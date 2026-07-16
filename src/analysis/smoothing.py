"""Signal smoothing (Migration Plan Phase 3 extraction).

Ported from Les Wright's baseline ``specFunctions.savitzky_golay`` (itself from
the SciPy cookbook), reimplemented with plain NumPy arrays instead of the
deprecated ``np.matrix``. Verified numerically equivalent to the baseline via
the golden regression fixtures (``tests/regression/golden/savgol.json``).

Original SciPy cookbook code: Copyright (c) 2001-2002 Enthought, Inc.,
2003-2022 SciPy Developers. BSD-3-Clause.
"""

from __future__ import annotations

from math import factorial

import numpy as np


def savitzky_golay(y, window_size, order, deriv=0, rate=1):
    """Smooth (and optionally differentiate) a 1-D signal with a Savitzky–Golay
    filter.

    Args:
        y: input samples (array-like).
        window_size: odd positive integer window length.
        order: polynomial order (must be <= window_size - 2).
        deriv: derivative order to compute (0 = smoothing).
        rate: sample rate, used when ``deriv`` > 0.

    Returns:
        ``np.ndarray`` the same length as ``y``.
    """
    y = np.asarray(y, dtype=float)
    try:
        window_size = np.abs(int(window_size))
        order = np.abs(int(order))
    except ValueError as exc:
        raise ValueError("window_size and order must be integers") from exc
    if window_size % 2 != 1 or window_size < 1:
        raise TypeError("window_size must be a positive odd number")
    if window_size < order + 2:
        raise TypeError("window_size is too small for the polynomial order")

    order_range = range(order + 1)
    half_window = (window_size - 1) // 2
    # Vandermonde design matrix over the window, then its pseudo-inverse row.
    b = np.array(
        [[k ** i for i in order_range] for k in range(-half_window, half_window + 1)],
        dtype=float,
    )
    m = np.linalg.pinv(b)[deriv] * rate ** deriv * factorial(deriv)
    # Pad the signal at both ends by reflecting around the endpoints.
    firstvals = y[0] - np.abs(y[1 : half_window + 1][::-1] - y[0])
    lastvals = y[-1] + np.abs(y[-half_window - 1 : -1][::-1] - y[-1])
    y = np.concatenate((firstvals, y, lastvals))
    return np.convolve(m[::-1], y, mode="valid")
