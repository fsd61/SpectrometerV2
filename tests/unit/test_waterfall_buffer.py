"""Tests for the Qt-free waterfall history buffer (ui.live.WaterfallBuffer)."""

import numpy as np
import pytest

from ui.live import WaterfallBuffer


def test_empty_until_first_push():
    buf = WaterfallBuffer(height=8)
    assert buf.image() is None
    assert buf.width is None


def test_shape_locked_on_first_push():
    buf = WaterfallBuffer(height=8)
    buf.push(np.arange(5.0))
    img = buf.image()
    assert img.shape == (8, 5)
    assert buf.width == 5


def test_newest_frame_is_row_zero_and_scrolls():
    buf = WaterfallBuffer(height=3)
    buf.push([1.0, 1.0])
    buf.push([2.0, 2.0])
    buf.push([3.0, 3.0])
    img = buf.image()
    assert list(img[0]) == [3.0, 3.0]   # newest on top
    assert list(img[1]) == [2.0, 2.0]
    assert list(img[2]) == [1.0, 1.0]
    # A fourth push evicts the oldest.
    buf.push([4.0, 4.0])
    img = buf.image()
    assert list(img[0]) == [4.0, 4.0]
    assert list(img[2]) == [2.0, 2.0]


def test_negatives_are_floored():
    buf = WaterfallBuffer(height=2)
    buf.push([-5.0, 3.0, -1.0])
    assert list(buf.image()[0]) == [0.0, 3.0, 0.0]


def test_width_mismatch_is_clipped_or_padded():
    buf = WaterfallBuffer(height=2)
    buf.push(np.ones(4))
    buf.push(np.ones(6) * 2)   # longer row: extra samples dropped
    assert buf.image().shape == (2, 4)
    assert list(buf.image()[0]) == [2.0, 2.0, 2.0, 2.0]
    buf.push(np.ones(2) * 3)   # shorter row: remainder zero-filled
    assert list(buf.image()[0]) == [3.0, 3.0, 0.0, 0.0]


def test_clear_resets():
    buf = WaterfallBuffer(height=4)
    buf.push([1.0, 2.0])
    buf.clear()
    assert buf.image() is None and buf.width is None


def test_invalid_height():
    with pytest.raises(ValueError):
        WaterfallBuffer(height=0)


# --------------------------------------------------------------------------- #
# Display levels: the waterfall must be readable as a measurement, so the
# colour scale may not re-base itself under the data on every repaint.
# --------------------------------------------------------------------------- #
def test_fixed_full_scale_is_used_verbatim():
    buf = WaterfallBuffer(height=4, full_scale=1023.0)
    buf.push([10.0, 20.0])
    assert buf.levels() == (0.0, 1023.0)
    # A much brighter frame does not move the ceiling.
    buf.push([900.0, 950.0])
    assert buf.levels() == (0.0, 1023.0)


def test_fixed_full_scale_keeps_a_dim_frame_dim():
    """The regression that autoLevels caused: a dim frame must not bloom."""
    buf = WaterfallBuffer(height=4, full_scale=255.0)
    buf.push([2.0, 3.0, 1.0])
    _lo, hi = buf.levels()
    assert max(buf.image()[0]) / hi < 0.02      # renders near-black, as it should


def test_auto_ceiling_tracks_the_whole_history_not_just_the_new_row():
    buf = WaterfallBuffer(height=3)
    buf.push([100.0, 50.0])
    buf.push([1.0, 2.0])
    # The bright frame is still in the buffer, so the scale must still span it.
    assert buf.levels() == (0.0, 100.0)


def test_auto_ceiling_drops_when_the_bright_frame_scrolls_off():
    buf = WaterfallBuffer(height=2)
    buf.push([100.0])
    buf.push([10.0])
    buf.push([5.0])          # evicts the 100
    assert buf.levels() == (0.0, 10.0)


def test_levels_never_degenerate():
    buf = WaterfallBuffer(height=2)
    assert buf.levels() == (0.0, 1.0)          # nothing pushed yet
    buf.push([0.0, 0.0])
    assert buf.levels() == (0.0, 1.0)          # an all-zero buffer


def test_levels_floor_is_always_zero():
    buf = WaterfallBuffer(height=2)
    buf.push([5.0, 9.0])
    assert buf.levels()[0] == 0.0


def test_invalid_full_scale():
    with pytest.raises(ValueError):
        WaterfallBuffer(height=4, full_scale=0.0)
    with pytest.raises(ValueError):
        WaterfallBuffer(height=4, full_scale=-1.0)
