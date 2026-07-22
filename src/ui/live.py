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

from dataclasses import dataclass, field
from typing import Optional, Protocol, Tuple

import numpy as np

from acquisition.service import acquire_spectrum
from analysis.pipeline import SpectralAnalysis, analyze
from cameras.base import CameraAdapter
from processing.spectrum import Spectrum
from synthetic.generator import SyntheticSpectrumSpec
from synthetic.stream import SyntheticStream

# A small demonstration line set (center nm, amplitude, FWHM nm) used for the
# synthetic live view; mirrors the CLI's demo lines.
DEMO_LINES = [
    (405.0, 200.0, 2.0), (436.0, 120.0, 1.5),
    (546.0, 180.0, 3.0), (612.0, 90.0, 2.0),
]


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


# --------------------------------------------------------------------------- #
# Frame sources — where live spectra come from (all Qt-free)
# --------------------------------------------------------------------------- #
class FrameSource(Protocol):
    """Anything that yields successive :class:`Spectrum` frames on demand."""

    def next_spectrum(self) -> Spectrum:
        ...

    def close(self) -> None:
        ...


@dataclass
class SyntheticFrameSource:
    """A hardware-free source that advances a reproducible synthetic stream."""

    stream: SyntheticStream
    _t: int = 0

    def next_spectrum(self) -> Spectrum:
        spectrum = self.stream.spectrum(self._t)
        self._t += 1
        return spectrum

    def close(self) -> None:  # nothing to release
        pass


@dataclass
class CameraFrameSource:
    """A source backed by a real camera adapter via the acquisition service."""

    camera: CameraAdapter
    center_row: Optional[int] = None
    average_rows: int = 3

    def next_spectrum(self) -> Spectrum:
        return acquire_spectrum(self.camera, self.center_row, self.average_rows)

    def close(self) -> None:
        try:
            self.camera.shutdown()
        except Exception:  # noqa: BLE001 - best-effort release
            pass


def build_synthetic_source(config) -> SyntheticFrameSource:
    """Build a synthetic frame source from the ``[synthetic]`` config section."""
    spec = SyntheticSpectrumSpec.from_config(
        config.section("synthetic"),
        [c for c, _, _ in DEMO_LINES], [a for _, a, _ in DEMO_LINES],
        per_line_fwhm=[f for _, _, f in DEMO_LINES],
    )
    return SyntheticFrameSource(stream=SyntheticStream(base=spec, drift_nm=2.0))


def build_frame_source(config, logger=None) -> FrameSource:
    """Build the live frame source implied by ``[camera] backend``.

    ``synthetic`` yields the hardware-free demo stream; any other backend builds
    and initializes the corresponding camera adapter. The GUI defaults to a
    synthetic source when no camera is configured, so it always has something to
    display.
    """
    backend = config.section("camera").get("backend", "synthetic")
    if backend == "synthetic":
        return build_synthetic_source(config)

    from cameras.factory import create_camera_from_config

    camera = create_camera_from_config(config.section("camera"))
    camera.initialize()
    proc = config.section("processing")
    slice_row = proc.get("slice_row", -1)
    center_row = None if slice_row is None or slice_row < 0 else int(slice_row)
    return CameraFrameSource(camera, center_row=center_row)


# --------------------------------------------------------------------------- #
# Live engine — one analyzed frame at a time (Qt-free)
# --------------------------------------------------------------------------- #
@dataclass
class LiveEngine:
    """Pulls a frame from a source and runs it through the analysis pipeline.

    This is the whole live loop minus the Qt timer/thread: the GUI's capture
    thread simply calls :meth:`step` repeatedly and paints the result.
    """

    source: FrameSource
    params: LiveParams = field(default_factory=LiveParams)

    def step(self) -> Tuple[Spectrum, SpectralAnalysis]:
        spectrum = self.source.next_spectrum()
        wavelengths = list(spectrum.wavelengths) if len(spectrum.wavelengths) else None
        result = analyze(
            spectrum.intensities, wavelengths=wavelengths, **self.params.analyze_kwargs()
        )
        return spectrum, result

    def close(self) -> None:
        self.source.close()


# --------------------------------------------------------------------------- #
# Waterfall history buffer (Qt-free)
# --------------------------------------------------------------------------- #
class WaterfallBuffer:
    """A fixed-height scrolling image of recent spectra (rows = time).

    The newest spectrum is row 0; older frames scroll toward the last row and
    fall off. The spectral width is locked on the first push. Negative values are
    floored at zero, matching the spectrum display (a detector reads no negative
    light). Qt-free so it is unit tested without a display; the widget just paints
    :meth:`image`.
    """

    def __init__(self, height: int = 256):
        if height < 1:
            raise ValueError("height must be >= 1")
        self.height = int(height)
        self.width: Optional[int] = None
        self._img: Optional[np.ndarray] = None

    def push(self, intensities) -> None:
        row = np.clip(np.asarray(intensities, dtype=float), 0.0, None)
        if self._img is None:
            self.width = len(row)
            self._img = np.zeros((self.height, self.width), dtype=float)
        w = min(self.width, len(row))
        self._img[1:] = self._img[:-1]      # scroll older frames down
        self._img[0, :] = 0.0
        self._img[0, :w] = row[:w]          # newest at the top

    def image(self) -> Optional[np.ndarray]:
        """The current 2-D image (rows = time, newest first), or None if empty."""
        return self._img

    def clear(self) -> None:
        self.width = None
        self._img = None


# --------------------------------------------------------------------------- #
# Readout rows for the control dock (Qt-free, testable)
# --------------------------------------------------------------------------- #
@dataclass
class PeakRow:
    """One row of the live peak readout table."""

    index: int
    position: float          # wavelength (nm) if calibrated, else pixel
    calibrated: bool
    intensity: float
    fwhm: Optional[float]    # nm if calibrated+measured, else pixels
    fwhm_calibrated: bool
    snr: Optional[float]


def peak_readout_rows(spectrum, result) -> list[PeakRow]:
    """Build display rows from an analyzed frame (used by the control dock)."""
    calibrated = len(spectrum.wavelengths) > 0
    rows: list[PeakRow] = []
    for i, p in enumerate(result.peaks, start=1):
        pos_calibrated = calibrated and p.wavelength is not None
        fwhm = p.fwhm_nm if p.fwhm_nm is not None else p.fwhm
        rows.append(
            PeakRow(
                index=i,
                position=p.wavelength if pos_calibrated else float(p.pixel),
                calibrated=pos_calibrated,
                intensity=float(p.intensity),
                fwhm=fwhm,
                fwhm_calibrated=p.fwhm_nm is not None,
                snr=p.snr,
            )
        )
    return rows
