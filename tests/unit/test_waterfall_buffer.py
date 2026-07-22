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
