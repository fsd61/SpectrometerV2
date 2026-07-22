"""Peak detection (Migration Plan Phase 3 extraction).

Ported verbatim in behavior from Les Wright's baseline
``specFunctions.peakIndexes`` (derived from *peakutils*). Verified equivalent to
the baseline via the golden regression fixtures
(``tests/regression/golden/peaks.json``).

peakutils: The MIT License (MIT), Copyright (c) 2014-2022 Lucas Hermann Negri.
"""

from __future__ import annotations

import numpy as np


def peak_indexes(y, thres=0.3, min_dist=1, thres_abs=False):
    """Return indices of the local maxima in ``y``.

    Args:
        y: signal (array-like, signed).
        thres: threshold; relative (fraction of the y range) unless
            ``thres_abs`` is True.
        min_dist: minimum separation between detected peaks, in samples.
        thres_abs: interpret ``thres`` as an absolute amplitude.

    Returns:
        ``np.ndarray`` of integer indices.
    """
    y = np.asarray(y)
    if np.issubdtype(y.dtype, np.unsignedinteger):
        raise ValueError("y must be signed")

    if not thres_abs:
        thres = thres * (np.max(y) - np.min(y)) + np.min(y)

    min_dist = int(min_dist)

    # First-order difference.
    dy = np.diff(y)

    # Fill in plateaus (runs of zero difference) so their edges are detected.
    (zeros,) = np.where(dy == 0)
    if len(zeros) == len(y) - 1:  # completely flat signal
        return np.array([])

    if len(zeros):
        zeros_diff = np.diff(zeros)
        (zeros_diff_not_one,) = np.add(np.where(zeros_diff != 1), 1)
        zero_plateaus = np.split(zeros, zeros_diff_not_one)

        if zero_plateaus[0][0] == 0:
            dy[zero_plateaus[0]] = dy[zero_plateaus[0][-1] + 1]
            zero_plateaus.pop(0)
        if len(zero_plateaus) and zero_plateaus[-1][-1] == len(dy) - 1:
            dy[zero_plateaus[-1]] = dy[zero_plateaus[-1][0] - 1]
            zero_plateaus.pop(-1)

        for plateau in zero_plateaus:
            median = np.median(plateau)
            dy[plateau[plateau < median]] = dy[plateau[0] - 1]
            dy[plateau[plateau >= median]] = dy[plateau[-1] + 1]

    # A peak is a +/- sign change in the derivative that is above threshold.
    peaks = np.where(
        (np.hstack([dy, 0.0]) < 0.0)
        & (np.hstack([0.0, dy]) > 0.0)
        & (np.greater(y, thres))
    )[0]

    # Enforce the minimum distance, keeping the highest peaks first.
    if peaks.size > 1 and min_dist > 1:
        highest = peaks[np.argsort(y[peaks])][::-1]
        rem = np.ones(y.size, dtype=bool)
        rem[peaks] = False
        for peak in highest:
            if not rem[peak]:
                sl = slice(max(0, peak - min_dist), peak + min_dist + 1)
                rem[sl] = True
                rem[peak] = False
        peaks = np.arange(y.size)[~rem]

    return peaks
