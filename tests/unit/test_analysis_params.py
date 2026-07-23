"""Tests for the Qt-free advanced-analysis parameter cores (ui.analysis_params).

These mirror the LiveParams tests: pure logic, no Qt, no display. The
subset-of-signature checks guard against the params drifting away from the
functions they feed (analysis.transforms / analysis.annealing)."""

import inspect

import pytest

from analysis.annealing import simulated_annealing
from analysis.transforms import wavelet_transform
from ui.analysis_params import SAFitParams, WaveletParams


# --------------------------------------------------------------------------- #
# WaveletParams
# --------------------------------------------------------------------------- #
def test_wavelet_choice_is_validated():
    p = WaveletParams()
    p.set_wavelet("sym5")
    assert p.wavelet == "sym5"
    with pytest.raises(ValueError):
        p.set_wavelet("db99")


def test_wavelet_level_clamps():
    p = WaveletParams(level=4)
    p.adjust_level(50)
    assert p.level == WaveletParams.LEVEL_MAX
    p.adjust_level(-999)
    assert p.level == WaveletParams.LEVEL_MIN


def test_effective_level_matches_pywt_clamping():
    # db4 has dec_len 8, so max level for 50 samples is floor(log2(50/7)) = 2.
    p = WaveletParams(wavelet="db4", level=4)
    assert p.effective_level(800) == 4        # requested fits
    assert p.effective_level(50) == 2         # clamped down
    assert p.effective_level(4) == 1          # tiny data floored to 1


def test_wavelet_to_kwargs_and_from_config():
    p = WaveletParams.from_config({"wavelet": "coif3", "level": 6})
    assert p.to_kwargs() == {"wavelet": "coif3", "level": 6}


def test_wavelet_kwargs_are_valid_for_wavelet_transform():
    allowed = set(inspect.signature(wavelet_transform).parameters)
    assert set(WaveletParams().to_kwargs()) <= allowed


# --------------------------------------------------------------------------- #
# SAFitParams
# --------------------------------------------------------------------------- #
def test_schedule_is_validated():
    p = SAFitParams()
    p.set_schedule("fast")
    assert p.schedule == "fast"
    with pytest.raises(ValueError):
        p.set_schedule("glacial")


def test_max_cycles_and_components_clamp():
    p = SAFitParams()
    p.adjust_max_cycles(10_000)
    assert p.max_cycles == SAFitParams.MAX_CYCLES_MAX
    p.set_n_components(999)
    assert p.n_components == SAFitParams.N_COMPONENTS_MAX
    p.set_n_components(-5)
    assert p.n_components == 0


def test_to_kwargs_auto_sentinels():
    p = SAFitParams(auto_T0=True, n_components=0, seed=7, lock_seed=True)
    kw = p.to_kwargs()
    assert kw["T0"] is None                 # auto-tune
    assert kw["n_components"] is None        # 0 -> auto (derive from peaks)
    assert kw["random_seed"] == 7           # locked seed is passed through


def test_to_kwargs_unlocked_seed_is_none():
    p = SAFitParams(seed=7, lock_seed=False)
    assert p.to_kwargs()["random_seed"] is None   # fresh RNG each run


def test_to_kwargs_explicit_components_and_T0():
    p = SAFitParams(auto_T0=False, T0=12.5, n_components=3)
    kw = p.to_kwargs()
    assert kw["T0"] == 12.5
    assert kw["n_components"] == 3


def test_toggle_lock_seed():
    p = SAFitParams(lock_seed=True)
    assert p.toggle_lock_seed() is False
    assert p.toggle_lock_seed() is True


def test_from_config_reads_annealing_section():
    p = SAFitParams.from_config(
        {"schedule": "slow", "max_cycles": 350, "tol": 1e-4,
         "n_components": 2, "bound_tightness": 0.8, "seed": 11, "lock_seed": False}
    )
    assert (p.schedule, p.max_cycles, p.n_components, p.seed, p.lock_seed) == (
        "slow", 350, 2, 11, False
    )


def test_sa_kwargs_are_valid_for_simulated_annealing():
    allowed = set(inspect.signature(simulated_annealing).parameters)
    assert set(SAFitParams().to_kwargs()) <= allowed
