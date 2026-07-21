"""Qt-free live-view core (Migration Plan Phase 7).

The interactive GUI is a thin PySide6 layer over this module. Everything with
real behavior — the tunable analysis parameters and (in later milestones) the
frame-source and step logic — lives here, with no Qt import, so it is unit
tested without a display. The Qt widgets only render what this core produces.

``LiveParams`` mirrors the original PySpectrometer2 live controls (savgol
polynomial order, peak min-distance, label threshold, hold-peaks, measure) with
the same bounds, exposed as pure, testable adjusters.
"""

from __future__ import annotations

from dataclasses import dataclass


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


@dataclass
class LiveParams:
    """Live, user-tunable analysis parameters for the interactive view.

    Bounds match the original tool's keybindings: savgol order 0-15, peak
    min-distance 0-100, threshold 0-1 (the original used 0-100; here it is a
    fraction so it feeds ``analyze`` directly).
    """

    savgol_window: int = 17
    savgol_order: int = 3          # "savpoly" (keys o / l)
    peak_thres: float = 0.2        # label threshold (keys u / j)
    peak_min_dist: int = 20        # "mindist" (keys i / k)
    measure: bool = False          # per-peak FWHM/SNR (key m)
    hold_peaks: bool = False       # freeze the running peak maxima (key h)

    # Bounds (inclusive).
    SAVGOL_ORDER_MIN = 0
    SAVGOL_ORDER_MAX = 15
    PEAK_MIN_DIST_MIN = 0
    PEAK_MIN_DIST_MAX = 100
    THRESHOLD_MIN = 0.0
    THRESHOLD_MAX = 1.0
    THRESHOLD_STEP = 0.05

    def adjust_savgol_order(self, delta: int) -> None:
        """Nudge the Savitzky-Golay polynomial order (keys o/l)."""
        self.savgol_order = _clamp(
            self.savgol_order + delta, self.SAVGOL_ORDER_MIN, self.SAVGOL_ORDER_MAX
        )

    def adjust_peak_min_dist(self, delta: int) -> None:
        """Nudge the minimum distance between detected peaks (keys i/k)."""
        self.peak_min_dist = _clamp(
            self.peak_min_dist + delta, self.PEAK_MIN_DIST_MIN, self.PEAK_MIN_DIST_MAX
        )

    def adjust_threshold(self, steps: int) -> None:
        """Nudge the peak-label threshold by ``steps`` increments (keys u/j)."""
        self.peak_thres = round(
            _clamp(
                self.peak_thres + steps * self.THRESHOLD_STEP,
                self.THRESHOLD_MIN,
                self.THRESHOLD_MAX,
            ),
            4,
        )

    def toggle_hold_peaks(self) -> bool:
        """Toggle hold-peaks (key h). Returns the new state."""
        self.hold_peaks = not self.hold_peaks
        return self.hold_peaks

    def toggle_measure(self) -> bool:
        """Toggle per-peak measurement (key m). Returns the new state."""
        self.measure = not self.measure
        return self.measure

    def analyze_kwargs(self) -> dict:
        """Keyword arguments for :func:`analysis.pipeline.analyze`."""
        return {
            "savgol_window": self.savgol_window,
            "savgol_order": self.savgol_order,
            "peak_thres": self.peak_thres,
            "peak_min_dist": self.peak_min_dist,
            "measure": self.measure,
        }
