"""Tests for the Qt-free peak readout rows (ui.live.peak_readout_rows)."""

from config.loader import load_config
from ui.live import LiveEngine, LiveParams, build_frame_source, peak_readout_rows


def _frame(measure):
    engine = LiveEngine(
        build_frame_source(load_config(overrides=["camera.backend=synthetic"])),
        LiveParams(measure=measure),
    )
    spectrum, result = engine.step()
    engine.close()
    return spectrum, result


def test_rows_calibrated_with_measurements():
    spectrum, result = _frame(measure=True)
    rows = peak_readout_rows(spectrum, result)
    assert len(rows) == 4
    first = rows[0]
    assert first.index == 1
    assert first.calibrated is True
    assert 400 <= first.position <= 410           # ~405 nm line
    assert first.fwhm is not None and first.fwhm_calibrated is True
    assert first.snr is not None and first.snr > 0


def test_rows_without_measurement_have_no_fwhm():
    spectrum, result = _frame(measure=False)
    rows = peak_readout_rows(spectrum, result)
    assert rows and all(r.fwhm is None and r.snr is None for r in rows)
    # Position is still the calibrated wavelength.
    assert rows[0].calibrated is True


def test_rows_uncalibrated_use_pixel_positions():
    # A Spectrum with no wavelength axis -> positions are pixel indices.
    from processing.spectrum import Spectrum
    from analysis.pipeline import analyze

    intensities = [0, 0, 0, 10, 40, 10, 0, 0, 0, 5, 30, 5, 0, 0]
    spectrum = Spectrum(wavelengths=[], intensities=intensities)
    result = analyze(intensities, wavelengths=None, savgol_window=5,
                     savgol_order=2, peak_thres=0.2, peak_min_dist=2)
    rows = peak_readout_rows(spectrum, result)
    assert rows and all(r.calibrated is False for r in rows)
    assert all(float(r.position).is_integer() for r in rows)
