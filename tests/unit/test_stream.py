"""Unit tests for the streaming synthetic source (Phase 4 extension)."""

from synthetic.generator import SyntheticSpectrumSpec
from synthetic.stream import SyntheticStream


def _stream(seed=7):
    base = SyntheticSpectrumSpec(
        center_wavelengths=[436.0, 546.0, 611.0], amplitudes=[120.0, 180.0, 90.0],
        per_line_fwhm=[2.0, 3.0, 2.0], snr=150.0, seed=seed,
    )
    return SyntheticStream(base=base, drift_nm=1.5)


def test_stream_is_deterministic():
    assert _stream().spectrum(3).intensities == _stream().spectrum(3).intensities


def test_stream_evolves_over_time():
    s = _stream()
    assert s.spectrum(0).intensities != s.spectrum(3).intensities


def test_frame_metadata_present():
    sp = _stream().spectrum(5)
    assert sp.metadata["frame_index"] == 5 and sp.metadata["stream"] is True


def test_iter_spectra_length_and_order():
    frames = list(_stream().iter_spectra(6))
    assert len(frames) == 6
    assert [f.metadata["frame_index"] for f in frames] == list(range(6))
