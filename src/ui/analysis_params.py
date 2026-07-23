"""Qt-free tunable parameters for the advanced-analysis GUI (Phase 7 prep).

These mirror :class:`ui.live.LiveParams`: pure, testable dataclasses that hold
the user-facing knobs for the two heavy analyses — wavelet decomposition
(:func:`analysis.transforms.wavelet_transform`) and simulated-annealing line
fitting (:func:`analysis.annealing.simulated_annealing`) — with curated choices,
clamped adjusters, ``from_config`` builders, and ``to_kwargs`` that map exactly
onto those functions' signatures. No Qt import, so the whole control surface is
unit-tested without a display; the widgets (a later milestone) only render this.

Design notes (grounded in the two signatures):

* Wavelet exposes only ``wavelet`` (curated family) and ``level``; ``level`` is
  clamped at compute time to what the sample count allows, so we compute the
  effective level here (without importing PyWavelets) for an honest readout.
* Simulated annealing exposes the *meaningful* knobs — schedule, compute budget,
  tolerance, component count, bound tightness, and the seed (surfaced and locked
  by default for reproducibility). The internal auto-tuned machinery (``T0``,
  step size, Markov factor, quench point) keeps its good defaults and is left off
  the config surface; override it via the constructor only when experimenting.
  ``x0``/``bounds``/``callback`` are supplied at call time (seeded from the
  detected peaks), never stored here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


# PyWavelets decomposition filter lengths (dec_len) for the curated families,
# so we can compute the max usable level without importing pywt: dbN/symN have
# dec_len = 2N, coifN has dec_len = 6N.
_DEC_LEN = {"db4": 8, "db6": 12, "sym5": 10, "coif3": 18}


@dataclass
class WaveletParams:
    """Tunable parameters for the wavelet decomposition view (keys: family, level)."""

    wavelet: str = "db4"
    level: int = 4
    # Which band the view overlays; runtime-only (not persisted to config).
    view_band: str = "approximation"

    WAVELET_CHOICES = ("db4", "db6", "sym5", "coif3")
    LEVEL_MIN = 1
    LEVEL_MAX = 12

    def set_wavelet(self, name: str) -> None:
        if name not in self.WAVELET_CHOICES:
            raise ValueError(
                f"unknown wavelet {name!r}; choose from {list(self.WAVELET_CHOICES)}"
            )
        self.wavelet = name

    def adjust_level(self, delta: int) -> None:
        self.level = _clamp(self.level + delta, self.LEVEL_MIN, self.LEVEL_MAX)

    def effective_level(self, n_samples: int) -> int:
        """The level actually used for ``n_samples`` points.

        Mirrors ``pywt.dwt_max_level`` clamping so the GUI can show the effective
        depth (which may be below the requested ``level``) without PyWavelets
        installed. Falls back to the requested level for unknown families.
        """
        dec_len = _DEC_LEN.get(self.wavelet)
        if dec_len is None or n_samples < dec_len:
            return max(1, min(self.level, 1))
        max_level = int(math.floor(math.log2(n_samples / (dec_len - 1))))
        max_level = max(1, max_level)
        return min(self.level, max_level)

    def to_kwargs(self) -> dict:
        """Keyword args for :func:`analysis.transforms.wavelet_transform`."""
        return {"wavelet": self.wavelet, "level": self.level}

    @classmethod
    def from_config(cls, section) -> "WaveletParams":
        """Build from a ``[wavelet]`` config section (dict-like)."""
        return cls(
            wavelet=str(section.get("wavelet", "db4")),
            level=int(section.get("level", 4)),
        )


@dataclass
class SAFitParams:
    """Tunable parameters for simulated-annealing line fitting.

    ``to_kwargs`` yields exactly the tunable keyword arguments of
    :func:`analysis.annealing.simulated_annealing`. The fit's ``objective``,
    ``x0``, ``bounds`` and ``callback`` are call-time concerns (seeded from the
    detected peaks and wired by the GUI), so they are deliberately not stored.
    """

    # Exposed / meaningful knobs.
    schedule: str = "medium"
    max_cycles: int = 200
    tol: float = 1e-5
    n_components: int = 0          # 0 = auto (derive from detected peaks)
    bound_tightness: float = 0.5   # used when deriving bounds from peaks
    seed: int = 0
    lock_seed: bool = True         # reproducibility by default

    # Advanced internals — good auto defaults; off the config surface.
    auto_T0: bool = True
    T0: Optional[float] = None
    step_size: float = 0.1
    markov_factor: int = 600
    quench_cycle: int = 12
    quench_decrement: float = 0.70

    SCHEDULE_CHOICES = ("fast", "medium", "slow")
    MAX_CYCLES_MIN = 1
    MAX_CYCLES_MAX = 5000
    TOL_MIN = 0.0
    TOL_MAX = 1.0
    N_COMPONENTS_MAX = 64
    TIGHTNESS_MIN = 0.0
    TIGHTNESS_MAX = 1.0

    def set_schedule(self, name: str) -> None:
        if name not in self.SCHEDULE_CHOICES:
            raise ValueError(
                f"unknown schedule {name!r}; choose from {list(self.SCHEDULE_CHOICES)}"
            )
        self.schedule = name

    def adjust_max_cycles(self, delta: int) -> None:
        self.max_cycles = _clamp(
            self.max_cycles + delta, self.MAX_CYCLES_MIN, self.MAX_CYCLES_MAX
        )

    def set_n_components(self, value: int) -> None:
        self.n_components = _clamp(int(value), 0, self.N_COMPONENTS_MAX)

    def set_bound_tightness(self, value: float) -> None:
        self.bound_tightness = _clamp(float(value), self.TIGHTNESS_MIN, self.TIGHTNESS_MAX)

    def toggle_lock_seed(self) -> bool:
        self.lock_seed = not self.lock_seed
        return self.lock_seed

    def to_kwargs(self) -> dict:
        """Keyword args for :func:`analysis.annealing.simulated_annealing`.

        ``n_components=0`` maps to ``None`` (auto), ``auto_T0`` maps ``T0`` to
        ``None`` (auto-tune), and an unlocked seed maps to ``None`` (fresh RNG).
        """
        return {
            "schedule": self.schedule,
            "T0": None if self.auto_T0 else self.T0,
            "n_components": None if self.n_components <= 0 else int(self.n_components),
            "markov_factor": int(self.markov_factor),
            "quench_cycle": int(self.quench_cycle),
            "quench_decrement": float(self.quench_decrement),
            "tol": float(self.tol),
            "max_cycles": int(self.max_cycles),
            "step_size": float(self.step_size),
            "random_seed": int(self.seed) if self.lock_seed else None,
        }

    @classmethod
    def from_config(cls, section) -> "SAFitParams":
        """Build from an ``[annealing]`` config section (dict-like)."""
        return cls(
            schedule=str(section.get("schedule", "medium")),
            max_cycles=int(section.get("max_cycles", 200)),
            tol=float(section.get("tol", 1e-5)),
            n_components=int(section.get("n_components", 0)),
            bound_tightness=float(section.get("bound_tightness", 0.5)),
            seed=int(section.get("seed", 0)),
            lock_seed=bool(section.get("lock_seed", True)),
        )
