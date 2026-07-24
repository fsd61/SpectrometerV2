"""Tests for the M5 GUI layer's Qt-free pieces: the keyboard-shortcut registry,
the snapshot/export helper, and pixel-mode readout formatting. None of these
import Qt, so they run without a display."""

from processing.spectrum import Spectrum
from data.sinks import read_csv_spectrum
from ui.live import (
    LIVE_SHORTCUTS,
    peak_readout_rows,
    snapshot_name,
    snapshot_spectrum,
)

# The 13 original PySpectrometer2 live keys.
_ORIGINAL_KEYS = set("hscxmpolikujq")


def test_registry_covers_the_thirteen_original_keys():
    keys = [s.key for s in LIVE_SHORTCUTS]
    assert len(keys) == 13
    assert len(set(keys)) == 13, "shortcut keys must be unique"
    assert set(keys) == _ORIGINAL_KEYS


def test_registry_specs_are_well_formed():
    menus = {"File", "Calibrate", "Analysis"}
    for s in LIVE_SHORTCUTS:
        assert len(s.key) == 1
        assert s.handler.startswith("act_")
        assert s.menu in menus
        assert s.label and s.tip


def test_only_toggle_actions_are_checkable():
    checkable = {s.key for s in LIVE_SHORTCUTS if s.checkable}
    assert checkable == set("hmp")  # hold, measure, pixel-mode


def test_snapshot_name_is_timestamped_to_the_millisecond():
    from datetime import datetime, timezone

    name = snapshot_name(datetime(2026, 7, 22, 19, 30, 0, 123456, tzinfo=timezone.utc))
    assert name == "snapshot-20260722T193000_123Z"


def test_snapshot_names_differ_within_the_same_second():
    from datetime import datetime, timezone

    t0 = datetime(2026, 7, 22, 19, 30, 0, 100000, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 22, 19, 30, 0, 900000, tzinfo=timezone.utc)
    # Two presses in the same second must not collide (the M8 field bug).
    assert snapshot_name(t0) != snapshot_name(t1)


def test_snapshot_spectrum_writes_through_the_sink(tmp_path):
    spec = Spectrum(
        wavelengths=[400.0, 500.0, 600.0],
        intensities=[1.0, 5.0, 2.0],
        metadata={"source": "synthetic"},
    )
    path = snapshot_spectrum(spec, tmp_path)
    assert path.exists()
    assert path.suffix == ".csv"
    # Round-trips through the same reader the CLI uses.
    back = read_csv_spectrum(path)
    assert list(back.intensities) == [1.0, 5.0, 2.0]
    assert (path.parent / f"{path.stem}.meta.json").exists()


class _FakePeak:
    def __init__(self, pixel, wavelength, intensity, fwhm, fwhm_nm, snr):
        self.pixel = pixel
        self.wavelength = wavelength
        self.intensity = intensity
        self.fwhm = fwhm
        self.fwhm_nm = fwhm_nm
        self.snr = snr


class _FakeResult:
    def __init__(self, peaks):
        self.peaks = peaks


def test_force_pixel_reports_pixels_even_when_calibrated():
    spectrum = Spectrum(wavelengths=[400.0, 500.0, 600.0], intensities=[0, 0, 0])
    result = _FakeResult([_FakePeak(1, 500.0, 9.0, 3.0, 0.6, 42.0)])

    nm_rows = peak_readout_rows(spectrum, result)
    assert nm_rows[0].calibrated is True
    assert nm_rows[0].position == 500.0
    assert nm_rows[0].fwhm_calibrated is True

    px_rows = peak_readout_rows(spectrum, result, force_pixel=True)
    assert px_rows[0].calibrated is False
    assert px_rows[0].position == 1.0          # the pixel index
    assert px_rows[0].fwhm_calibrated is False  # width now in pixels
    assert px_rows[0].fwhm == 3.0
