"""Unit tests for the shared Spectrum data object."""

import pytest

from processing import Spectrum


def test_length_and_metadata():
    s = Spectrum(wavelengths=[400.0, 401.0], intensities=[1.0, 2.0], metadata={"src": "test"})
    assert len(s) == 2
    assert s.metadata["src"] == "test"


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        Spectrum(wavelengths=[400.0, 401.0], intensities=[1.0])


def test_empty_wavelengths_allowed():
    s = Spectrum(wavelengths=[], intensities=[1.0, 2.0, 3.0])
    assert len(s) == 3
