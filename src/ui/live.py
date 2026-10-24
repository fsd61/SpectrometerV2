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
from datetime import datetime, timezone
from typing import Optional, Protocol, Tuple

import numpy as np

from acquisition.service import acquire_spectrum, extraction_settings
from analysis.pipeline import SpectralAnalysis, analyze
from cameras.base import CameraAdapter
from processing.extraction import PRECISIONS
from processing.spectrum import Spectrum
from ui.analysis_params import WaveletParams
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
    pixel_mode: bool = False       # label peaks in pixels, not nm (key p)

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
        """Toggle per-peak measurement (key m). Returns the new state.

        Mirrors the original tool: enabling measure turns off pixel-position
        mode (the two are mutually exclusive readouts).
        """
        self.measure = not self.measure
        if self.measure:
            self.pixel_mode = False
        return self.measure

    def toggle_pixel_mode(self) -> bool:
        """Toggle pixel-position labelling (key p). Returns the new state.

        Mirrors the original ``recPixels``: enabling it turns off measure, and
        forces peak positions/FWHM to display in pixels even when a wavelength
        calibration is present.
        """
        self.pixel_mode = not self.pixel_mode
        if self.pixel_mode:
            self.measure = False
        return self.pixel_mode

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
    """A hardware-free source that advances a reproducible synthetic stream.

    The underlying spec can be swapped live (:meth:`set_spec`) — this is what the
    GUI's synthetic-source panel edits — and drift toggled (:meth:`set_drift`).
    """

    stream: SyntheticStream
    _t: int = 0

    @property
    def spec(self) -> SyntheticSpectrumSpec:
        return self.stream.base

    def set_spec(self, spec: SyntheticSpectrumSpec) -> None:
        # Single reference assignment: safe to call from the UI thread while the
        # capture thread reads ``stream.base`` each frame.
        self.stream.base = spec

    def set_drift(self, enabled: bool, drift_nm: float = 2.0) -> None:
        self.stream.drift_nm = float(drift_nm) if enabled else 0.0

    def next_spectrum(self) -> Spectrum:
        spectrum = self.stream.spectrum(self._t)
        self._t += 1
        return spectrum

    def close(self) -> None:  # nothing to release
        pass


@dataclass
class SyntheticPeak:
    """One editable synthetic line: center wavelength (nm), amplitude, FWHM (nm)."""

    wavelength: float
    amplitude: float
    fwhm: float


def build_synthetic_spec(
    peaks,
    *,
    snr: float,
    baseline: float,
    sample_interval: float,
    seed: int,
    wavelength_min: float = 380.0,
    wavelength_max: float = 750.0,
    profile_type: str = "gaussian",
) -> SyntheticSpectrumSpec:
    """Build a :class:`SyntheticSpectrumSpec` from editable peak rows + globals."""
    return SyntheticSpectrumSpec(
        center_wavelengths=[float(p.wavelength) for p in peaks],
        amplitudes=[float(p.amplitude) for p in peaks],
        per_line_fwhm=[float(p.fwhm) for p in peaks],
        snr=float(snr),
        baseline=float(baseline),
        sample_interval=float(sample_interval),
        seed=int(seed),
        wavelength_min=float(wavelength_min),
        wavelength_max=float(wavelength_max),
        profile_type=profile_type,
    )


def spec_to_peaks(spec: SyntheticSpectrumSpec) -> list[SyntheticPeak]:
    """Read a spec's lines back into editable :class:`SyntheticPeak` rows."""
    n = len(spec.center_wavelengths)
    if spec.per_line_fwhm and len(spec.per_line_fwhm) == n:
        fwhms = list(spec.per_line_fwhm)
    else:
        fwhms = [float(spec.fwhm)] * n
    return [
        SyntheticPeak(float(w), float(a), float(f))
        for w, a, f in zip(spec.center_wavelengths, spec.amplitudes, fwhms)
    ]


@dataclass
class CameraFrameSource:
    """A source backed by a real camera adapter via the acquisition service."""

    camera: CameraAdapter
    center_row: Optional[int] = None
    average_rows: int = 3
    precision: str = "integer"
    frame_height: Optional[int] = None   # learned from the first frame

    def next_spectrum(self) -> Spectrum:
        spectrum = acquire_spectrum(self.camera, self.center_row, self.average_rows, self.precision)
        self.frame_height = int(spectrum.metadata.get("height", 0)) or self.frame_height
        return spectrum

    def max_band_height(self) -> Optional[int]:
        """Tallest odd band that fits the frame about the current center row."""
        if not self.frame_height:
            return None
        center = self.frame_height // 2 if self.center_row is None else int(self.center_row)
        half = min(center, self.frame_height - 1 - center)
        return 2 * half + 1

    def set_extraction(self, average_rows: Optional[int] = None,
                       precision: Optional[str] = None) -> None:
        """Change the extraction band live (GUI). Validated here, before the
        capture thread uses it, so a bad value can never stop acquisition.

        Plain attribute assignment, read by the capture thread on its next
        frame (same pattern as ``SyntheticFrameSource.set_spec``).
        """
        if average_rows is not None:
            rows = int(average_rows)
            if rows < 1 or rows % 2 == 0:
                raise ValueError("slice height must be a positive odd number of rows")
            limit = self.max_band_height()
            if limit is not None and rows > limit:
                raise ValueError(f"slice height {rows} does not fit the frame (max {limit})")
            self.average_rows = rows
        if precision is not None:
            if precision not in PRECISIONS:
                raise ValueError(f"precision must be one of {PRECISIONS}")
            self.precision = precision

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
    return CameraFrameSource(camera, **extraction_settings(config.section("processing")))


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
    calibration: Optional[list] = None   # per-pixel wavelengths (nm), or None
    calibration_meta: dict = field(default_factory=dict)
    wavelet: WaveletParams = field(default_factory=WaveletParams)
    denoise_error: Optional[str] = None  # set if denoising could not run
    _hold: Optional[np.ndarray] = field(default=None, repr=False)

    def set_calibration(self, wavelengths, result=None) -> None:
        """Apply a pixel->wavelength calibration to subsequent uncalibrated frames.

        Passing the :class:`~calibration.wavelength.CalibrationResult` as
        ``result`` records the fit itself — coefficients, order, and a
        fingerprint — on every frame the calibration is applied to. Without it
        the persisted record can say a spectrum is calibrated but not *which*
        calibration produced it, which is precisely the provenance gap that
        lets two different wavelength axes be plotted as one series.

        Single reference assignment, so it is safe to call from the UI thread
        while the capture thread reads it each frame (same pattern as
        ``SyntheticFrameSource.set_spec``).
        """
        meta: dict = {}
        if result is not None:
            from data.schema_core import calibration_fingerprint

            coefficients = [float(c) for c in result.coefficients]
            width = len(result.wavelengths)
            meta = {
                "calibration_coefficients": coefficients,
                "calibration_order": int(result.order),
                "calibration_r_squared": result.r_squared,
                "calibration_id": calibration_fingerprint(
                    coefficients, int(result.order), width
                ),
            }
        # Assign the payload before the flag the capture thread tests on, so a
        # frame can never see a calibration without its identity.
        self.calibration_meta = meta
        self.calibration = list(wavelengths) if wavelengths is not None else None

    def clear_calibration(self) -> None:
        self.calibration = None
        self.calibration_meta = {}

    def step(self) -> Tuple[Spectrum, SpectralAnalysis]:
        spectrum = self.source.next_spectrum()

        # Hold-peaks (key h): accumulate the element-wise maximum across frames
        # so transient/flickering lines are frozen at their brightest. Toggling
        # it off clears the accumulator; a width change resets it safely.
        if self.params.hold_peaks:
            intensities = np.asarray(spectrum.intensities, dtype=float)
            if self._hold is None or self._hold.shape != intensities.shape:
                self._hold = intensities.copy()
            else:
                np.maximum(self._hold, intensities, out=self._hold)
            spectrum = Spectrum(
                wavelengths=list(spectrum.wavelengths),
                intensities=self._hold.tolist(),
                metadata={**spectrum.metadata, "hold_peaks": True},
            )
        else:
            self._hold = None

        # Click-to-calibrate (M6): attach the fitted wavelength axis to frames
        # that arrive uncalibrated (the camera path). Frames that already carry
        # wavelengths (synthetic ground truth) are left untouched — a user
        # calibration must never overwrite a known-true axis.
        if self.calibration is not None and len(spectrum.wavelengths) == 0:
            n = len(spectrum.intensities)
            spectrum = Spectrum(
                wavelengths=[float(w) for w in self.calibration[:n]],
                intensities=spectrum.intensities,
                metadata={
                    **spectrum.metadata,
                    "calibration": "applied",
                    **self.calibration_meta,
                },
            )

        wavelengths = list(spectrum.wavelengths) if len(spectrum.wavelengths) else None

        # Optional wavelet-denoising stage. It reads the raw spectrum and never
        # replaces it: smoothing and peak detection see the denoised series,
        # while FWHM/SNR are measured on the raw one (a denoised trace has
        # artificially low noise). The Spectrum keeps the raw data, so
        # snapshots stay raw and record the stage in their metadata.
        denoised = None
        if self.wavelet.denoise:
            denoised = self._denoise(spectrum.intensities)
        if denoised is not None:
            kwargs = self.wavelet.denoise_kwargs()
            spectrum = Spectrum(
                wavelengths=spectrum.wavelengths, intensities=spectrum.intensities,
                metadata={**spectrum.metadata, "wavelet_denoise": kwargs},
            )
            result = analyze(denoised, wavelengths=wavelengths,
                             measure_on=spectrum.intensities, **self.params.analyze_kwargs())
            result.denoised = [float(v) for v in denoised]
        else:
            result = analyze(
                spectrum.intensities, wavelengths=wavelengths, **self.params.analyze_kwargs()
            )
        return spectrum, result

    def _denoise(self, intensities):
        """Denoise for the analysis, or None (with ``denoise_error`` set) if
        PyWavelets is missing or the transform fails; capture never stops."""
        try:
            from analysis.transforms import wavelet_denoise

            out = wavelet_denoise(intensities, **self.wavelet.denoise_kwargs()).denoised
            self.denoise_error = None
            return out
        except Exception as exc:  # noqa: BLE001 - surface in the UI, keep capturing
            self.denoise_error = str(exc)
            return None

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
    :meth:`image` between :meth:`levels`.

    ``full_scale`` fixes the display ceiling in raw detector units (255 for an
    8-bit path, 1023 for 10-bit). It is what makes a waterfall a measurement
    rather than a picture: with a fixed ceiling a dim frame renders dim and rows
    stay comparable down the time axis. Left unset, the ceiling tracks the
    brightest sample *currently held in the buffer* - still a relative scale, but
    a stable one that only moves when a frame enters or leaves the history.
    Per-frame renormalization (pyqtgraph's ``autoLevels``) is deliberately not
    used: it re-bases brightness every repaint, so a noise-only frame blooms to
    full scale and no two rows can be compared - destroying the one thing the
    waterfall exists to show.
    """

    def __init__(self, height: int = 256, full_scale: Optional[float] = None):
        if height < 1:
            raise ValueError("height must be >= 1")
        if full_scale is not None and float(full_scale) <= 0:
            raise ValueError("full_scale must be > 0 when given")
        self.height = int(height)
        self.full_scale = float(full_scale) if full_scale is not None else None
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

    def levels(self) -> Tuple[float, float]:
        """The ``(low, high)`` intensity range the image should be painted over.

        Floor is always 0 (a detector reads no negative light, and a floating
        floor would make the background brightness meaningless). Ceiling is
        ``full_scale`` when configured, else the brightest sample still in the
        history. The fallback never returns 0 as the ceiling - an all-zero buffer
        would otherwise give a degenerate range.
        """
        if self.full_scale is not None:
            return (0.0, self.full_scale)
        if self._img is None:
            return (0.0, 1.0)
        peak = float(self._img.max())
        return (0.0, peak if peak > 0.0 else 1.0)

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


def peak_readout_rows(spectrum, result, force_pixel: bool = False) -> list[PeakRow]:
    """Build display rows from an analyzed frame (used by the control dock).

    When ``force_pixel`` is set (pixel-mode, key p), positions and widths are
    reported in pixels even if the spectrum carries a wavelength calibration.
    """
    calibrated = len(spectrum.wavelengths) > 0 and not force_pixel
    rows: list[PeakRow] = []
    for i, p in enumerate(result.peaks, start=1):
        pos_calibrated = calibrated and p.wavelength is not None
        fwhm = p.fwhm_nm if (pos_calibrated and p.fwhm_nm is not None) else p.fwhm
        rows.append(
            PeakRow(
                index=i,
                position=p.wavelength if pos_calibrated else float(p.pixel),
                calibrated=pos_calibrated,
                intensity=float(p.intensity),
                fwhm=fwhm,
                fwhm_calibrated=pos_calibrated and p.fwhm_nm is not None,
                snr=p.snr,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Snapshot / export (Qt-free) — writes through the pluggable data sink
# --------------------------------------------------------------------------- #
def snapshot_name(now: Optional[datetime] = None) -> str:
    """A UTC-timestamped snapshot base name, e.g.
    ``snapshot-20260722T193000_123Z``.

    Millisecond precision so pressing the snapshot key several times within the
    same second produces distinct files instead of overwriting one.
    """
    now = now or datetime.now(timezone.utc)
    return (
        "snapshot-"
        + now.strftime("%Y%m%dT%H%M%S_")
        + f"{now.microsecond // 1000:03d}Z"
    )


def snapshot_spectrum(spectrum, directory, name: Optional[str] = None, sink=None):
    """Export the current spectrum through a :class:`data.sinks.SpectrumSink`.

    Returns the primary (CSV) path. The snapshot key (``s``) calls this; keeping
    it here (Qt-free) means the save path is unit-tested without a display.

    ``sink`` is the sink assembled by :func:`data.factory.build_sink`, so a GUI
    snapshot lands in *every* enabled store — SQLite and InfluxDB included —
    exactly as a CLI run does. Without it the GUI, which is the primary
    interface, would be invisible to the telemetry it is meant to feed. It
    falls back to CSV-only when no sink is supplied (tests, headless callers).
    """
    if sink is None:
        from data.sinks import CsvSpectrumSink

        sink = CsvSpectrumSink(directory)
    return sink.write(spectrum, name=name or snapshot_name())


# --------------------------------------------------------------------------- #
# Live keyboard-shortcut registry (Qt-free, data-driven)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ShortcutSpec:
    """One live keyboard shortcut, mirroring an original PySpectrometer2 key.

    The Qt layer iterates this registry to build the menu bar, the toolbar, and
    the ``QShortcut``/``QAction`` bindings, connecting each ``handler`` (a method
    name on the main window) to its key. Keeping it here (Qt-free) means the set
    of shortcuts, their menus, and their labels are unit-tested without a display.
    """

    key: str          # single character, matches the original tool
    handler: str      # MainWindow method bound to the action
    label: str        # menu / action text
    menu: str         # which top-level menu it belongs to
    tip: str          # status-bar / tooltip text
    toolbar: bool = False
    checkable: bool = False


# The 13 original keys: h s c x m p o l i k u j q.
LIVE_SHORTCUTS: Tuple[ShortcutSpec, ...] = (
    ShortcutSpec("s", "act_snapshot", "Snapshot / export",
                 "File", "Save the current spectrum (CSV + metadata)", toolbar=True),
    ShortcutSpec("q", "act_quit", "Quit", "File", "Close the spectrometer window"),
    ShortcutSpec("c", "act_calibrate", "Apply calibration",
                 "Calibrate", "Fit wavelength calibration from picked points", toolbar=True),
    ShortcutSpec("x", "act_clear_calibration", "Clear calibration points",
                 "Calibrate", "Discard the pending calibration points"),
    ShortcutSpec("h", "act_toggle_hold", "Hold peaks",
                 "Analysis", "Freeze the running peak maxima", toolbar=True, checkable=True),
    ShortcutSpec("m", "act_toggle_measure", "Measure FWHM / SNR",
                 "Analysis", "Measure each peak's width and signal-to-noise",
                 toolbar=True, checkable=True),
    ShortcutSpec("p", "act_toggle_pixel", "Pixel positions",
                 "Analysis", "Label peaks in pixels instead of nm",
                 toolbar=True, checkable=True),
    ShortcutSpec("o", "act_savgol_up", "Smoothing order +",
                 "Analysis", "Increase the Savitzky-Golay polynomial order"),
    ShortcutSpec("l", "act_savgol_down", "Smoothing order -",
                 "Analysis", "Decrease the Savitzky-Golay polynomial order"),
    ShortcutSpec("i", "act_mindist_up", "Peak min-distance +",
                 "Analysis", "Increase the minimum spacing between peaks"),
    ShortcutSpec("k", "act_mindist_down", "Peak min-distance -",
                 "Analysis", "Decrease the minimum spacing between peaks"),
    ShortcutSpec("u", "act_thresh_up", "Threshold +",
                 "Analysis", "Raise the peak-label threshold"),
    ShortcutSpec("j", "act_thresh_down", "Threshold -",
                 "Analysis", "Lower the peak-label threshold"),
)


# --------------------------------------------------------------------------- #
# Click-to-calibrate (M6) — Qt-free session model
# --------------------------------------------------------------------------- #
def snap_pixel_to_peak(x_pixel, peak_pixels, tol: int = 12) -> int:
    """Snap a clicked plot x to the nearest detected peak pixel within ``tol``.

    Picking calibration lines is easier if a near-miss click lands exactly on the
    detected peak; clicks further than ``tol`` px from any peak keep the rounded
    click position (so lines the detector missed can still be picked).
    """
    x = int(round(float(x_pixel)))
    if not peak_pixels:
        return x
    nearest = min(peak_pixels, key=lambda p: abs(int(p) - x))
    return int(nearest) if abs(int(nearest) - x) <= tol else x


@dataclass
class CalibrationSession:
    """Pending pixel->wavelength calibration points picked from the plot.

    The GUI appends a point per click (key/menu-gated pick mode); ``c`` fits and
    applies once at least three points exist, ``x`` clears them. The fit and the
    file format delegate to the existing ``calibration`` package, so the GUI and
    CLI produce identical, interoperable calibrations.
    """

    points: list = field(default_factory=list)   # list[(pixel:int, wavelength:float)]

    def add(self, pixel, wavelength) -> None:
        self.points.append((int(round(float(pixel))), float(wavelength)))

    def remove_last(self) -> None:
        if self.points:
            self.points.pop()

    def clear(self) -> None:
        self.points.clear()

    @property
    def count(self) -> int:
        return len(self.points)

    @property
    def ready(self) -> bool:
        """A polynomial fit needs at least three points (2nd order)."""
        return len(self.points) >= 3

    def pixels(self) -> list:
        return [p for p, _ in self.points]

    def wavelengths(self) -> list:
        return [w for _, w in self.points]

    def fit(self, width: int, pixels=None):
        """Fit the pixel->wavelength polynomial over a sensor ``width`` px wide.

        ``pixels`` overrides the picked whole-pixel positions, e.g. with the
        sub-pixel centers from :meth:`fitted_pixels`.
        """
        from calibration.wavelength import calibrate

        return calibrate(self.pixels() if pixels is None else list(pixels),
                         self.wavelengths(), width)

    def axis(self, width: int) -> list:
        """The per-pixel wavelength axis produced by the current points."""
        return self.fit(width).wavelengths

    def fitted_pixels(self, intensities, merge_px: float = 10.0, **fit_kwargs) -> list:
        """Sub-pixel line centers for the picks, fitted on ``intensities``.

        Picks within ``merge_px`` of each other are fitted together, so both
        halves of a doublet get their own center.
        """
        from analysis.linefit import refine_centers

        return refine_centers(intensities, self.pixels(), merge_px=merge_px, **fit_kwargs)

    def save(self, path, pixels=None):
        """Persist the points in the baseline caldata format (``pixels``
        overrides the picked positions, as in :meth:`fit`)."""
        from calibration.persistence import write_calibration_points

        return write_calibration_points(
            path, self.pixels() if pixels is None else list(pixels), self.wavelengths())


# --------------------------------------------------------------------------- #
# A/B check: whole-pixel picks vs fitted line centers (Qt-free)
# --------------------------------------------------------------------------- #
@dataclass
class CentroidRow:
    wavelength: float          # known line wavelength, nm
    pick_px: float             # whole-pixel pick
    fitted_px: float           # sub-pixel center from line fitting
    residual_pick: float       # leave-one-out prediction error, nm
    residual_fitted: float


@dataclass
class CentroidComparison:
    rows: list                 # list[CentroidRow], in pick order
    rms_pick: float            # nm
    rms_fitted: float          # nm

    @property
    def improvement(self) -> Optional[float]:
        """Fractional reduction of the RMS residual by fitted centers."""
        if self.rms_pick <= 0:
            return None
        return 1.0 - self.rms_fitted / self.rms_pick


def compare_centroid_methods(session: CalibrationSession, intensities,
                             merge_px: float = 10.0, **fit_kwargs) -> CentroidComparison:
    """Compare calibration accuracy with whole-pixel picks vs fitted centers.

    Each calibration line is left out in turn, the calibration is fitted to the
    rest, and the error predicting the left-out line is recorded -- for the
    picked positions and for the fitted ones. The difference isolates the
    effect of line-center precision on wavelength accuracy. Needs 4+ points.
    """
    from calibration.wavelength import leave_one_out_residuals

    picks = [float(p) for p in session.pixels()]
    wavelengths = session.wavelengths()
    fitted = session.fitted_pixels(intensities, merge_px=merge_px, **fit_kwargs)
    res_pick = leave_one_out_residuals(picks, wavelengths)
    res_fit = leave_one_out_residuals(fitted, wavelengths)
    rows = [CentroidRow(w, p, f, rp, rf)
            for w, p, f, rp, rf in zip(wavelengths, picks, fitted, res_pick, res_fit)]
    rms = lambda r: float(np.sqrt(np.mean(np.square(r))))  # noqa: E731
    return CentroidComparison(rows=rows, rms_pick=rms(res_pick), rms_fitted=rms(res_fit))
