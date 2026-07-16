"""Unit tests for the synthetic spectrum generator (Phase 4; SYN-001..009)."""

import pytest

from synthetic.generator import SyntheticSpectrumSpec, generate


def _spec(**kw):
    base = dict(
        center_wavelengths=[500.0], amplitudes=[100.0],
        wavelength_min=400.0, wavelength_max=600.0, sample_interval=0.5,
        snr=100.0, seed=7,
    )
    base.update(kw)
    return SyntheticSpectrumSpec(**base)


def test_reproducible_same_seed():
    assert generate(_spec()).intensities == generate(_spec()).intensities


def test_seed_changes_noise():
    assert generate(_spec(seed=1)).intensities != generate(_spec(seed=2)).intensities


def test_axis_bounds_and_spacing():
    s = generate(_spec(wavelength_min=400, wavelength_max=600, sample_interval=0.5))
    wl = s.wavelengths
    assert wl[0] == pytest.approx(400.0)
    assert wl[-1] == pytest.approx(600.0)
    assert wl[1] - wl[0] == pytest.approx(0.5)
    assert len(s) == len(wl) == 401


def test_noiseless_when_snr_zero():
    s = generate(_spec(snr=0))
    assert max(s.intensities) == pytest.approx(100.0, abs=1e-9)


def test_baseline_and_slope_applied():
    s = generate(_spec(amplitudes=[0.0], snr=0, baseline=10.0, baseline_slope=0.1,
                       wavelength_min=400, wavelength_max=600, sample_interval=1.0))
    assert s.intensities[0] == pytest.approx(10.0)
    assert s.intensities[-1] == pytest.approx(10.0 + 0.1 * 200)


def test_per_line_fwhm_length_mismatch_raises():
    with pytest.raises(ValueError):
        generate(_spec(center_wavelengths=[500, 510], amplitudes=[100, 100], per_line_fwhm=[2.0]))


def test_centers_amplitudes_mismatch_raises():
    with pytest.raises(ValueError):
        generate(_spec(center_wavelengths=[500, 510], amplitudes=[100]))


def test_unsupported_profile_raises():
    with pytest.raises(NotImplementedError):
        generate(_spec(profile_type="lorentzian"))


def test_metadata_is_complete():
    s = generate(_spec())
    for key in ("source", "generator", "profile_type", "center_wavelengths",
                "amplitudes", "fwhm", "wavelength_min", "wavelength_max",
                "sample_interval", "snr", "noise_sigma", "baseline",
                "baseline_slope", "seed", "n_samples"):
        assert key in s.metadata, f"missing metadata key {key}"
    assert s.metadata["source"] == "synthetic"


def test_from_config_builds_spec():
    from config import load_config
    cfg = load_config("config/default.ini")
    spec = SyntheticSpectrumSpec.from_config(cfg.section("synthetic"), [500.0], [100.0])
    assert spec.wavelength_min == 380.0
    assert spec.profile_type == "gaussian"
    assert spec.center_wavelengths == [500.0]
