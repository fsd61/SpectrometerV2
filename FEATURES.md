# Features Added Since PySpectrometer2

**Baseline:** Les Wright's PySpectrometer2, preserved under
`Original_Pyspectrometer2/` at tag `baseline-v1.0` — 1,384 lines across three
files, no tests, no configuration, no logging.

**Current:** 6,724 lines of application code, 3,622 lines of tests, 328 passing
tests.

This document lists what is *new*. The scientific behavior of the baseline is
deliberately unchanged and is pinned by golden regression tests — see
[Preserved Unchanged](#preserved-unchanged) below. For the full catalog of what
the baseline did, see `Docs/Legacy_Feature_Inventory.md`; for provenance and
credit, `ATTRIBUTION.md` and `NOTICE`.

---

## 1. Platform portability

| | Baseline | Now |
|---|---|---|
| USB capture | `cv2.VideoCapture('/dev/video<N>', cv2.CAP_V4L)` — Linux only | Device *index*, default OpenCV backend — Linux, Windows, macOS, Pi |
| Pi capture | Separate 465-line script | Adapter behind the shared camera contract |
| Platform logic | None | `platforms/` with runtime detection and per-platform recommendations |

Linux, Windows, and Raspberry Pi are equal first-class targets. The baseline's
hard-coded V4L device path was the single largest portability blocker.

## 2. Architecture

- **Camera contract** (`cameras/base.py`) with three adapters — USB, Picamera2,
  synthetic — selected by a factory. The baseline shipped two ~90% identical
  main scripts that differed only in their acquisition block; that duplication
  is gone.
- **Separated concerns.** Acquisition, processing, calibration, analysis,
  persistence and UI are distinct packages. The baseline held all of it in one
  module-level script with global state.
- **Platform-neutral scientific core.** No OS or camera specifics below the
  adapter layer.
- **Exception hierarchy** (`errors.py`) — a single base class with precise
  subtypes, replacing bare `print()` diagnostics.

## 3. Configuration

Entirely new; the baseline had no configuration file.

- **12 documented INI sections**: `general`, `logging`, `camera`, `gui`,
  `processing`, `calibration`, `synthetic`, `wavelet`, `annealing`, `sqlite`,
  `influx`, `user_schema`.
- **Schema-validated** with types, ranges, and choices — invalid values are
  rejected at startup rather than failing later.
- **Self-documenting**: `init-config` generates a fully-commented file from the
  schema; `describe-config` prints it.
- **Auto-discovery** from the project root, so it works from any subdirectory.
- **Per-run overrides** via repeatable `--set SECTION.KEY=VALUE`, with no file
  edit required.
- Every hard-coded baseline parameter — frame size, fps, Savitzky–Golay window,
  peak min-distance, threshold, crop origin, row averaging, gain, calibration
  path — is now externalized.

## 4. Logging

Entirely new. Structured logging with rotating file handlers, configurable
level, directory, size and backup count, and an optional console stream. The
baseline used `print()`.

## 5. Command-line interface

| | Baseline | Now |
|---|---|---|
| Options | 4 (`--device`, `--fps`, `--fullscreen`, `--waterfall`) | 8 global options |
| Commands | — | 11 subcommands |
| Headless | No | Yes — full pipeline with no display |

Commands: `run`, `gui`, `generate-synthetic`, `stream`, `analyze`,
`test-camera`, `verify-hardware`, `check-calibration`, `validate-config`,
`describe-config`, `init-config`.

Global options are accepted **on either side of the subcommand**, which argparse
does not do by default — `spectrometerv2 stream --frames 60` and
`spectrometerv2 --frames 60 stream` are equivalent. Repeatable options (`--set`,
`-v`) merge across the two sides rather than one silently replacing the other.

## 6. Graphical interface

The baseline drew two OpenCV windows with single-key bindings. Added:

- **PySide6 + pyqtgraph desktop GUI** with a live spectrum view and waterfall.
- **Graticule overlay** rendered against the calibrated axis.
- **Waterfall controls** — configurable frame depth, colormap (five perceptually
  uniform choices), fixed or auto intensity ceiling, and a raw/smoothed source
  selector. A fixed ceiling keeps brightness comparable between sessions, which
  the baseline's auto-scaling could not.
- **Synthetic signal dock** — live editable peak table and seed control, clearly
  labelled as simulated.
- The GUI is optional and dependency-gated; the application runs fully headless
  without it.

## 7. Analysis

Baseline: Savitzky–Golay smoothing, peak detection, polynomial calibration,
graticule, wavelength→RGB. All preserved. Added:

- **Gaussian line fitting**, **FWHM**, and **SNR estimation** (`measurements.py`)
- **FFT** and **wavelet decomposition** (`transforms.py`, optional `pywt`)
- **Simulated-annealing global optimizer** (`annealing.py`) for multi-component
  line fitting, with a seeded RNG for reproducibility
- **End-to-end analysis pipeline** (`pipeline.py`) returning a structured result
  rather than printing

The FFT, wavelet and annealing functions existed in the `Wtx+SA` patch superset
(`Docs/reference/`) but were never part of the shipped baseline. They are now
first-class, dependency-gated, and tested.

## 8. Synthetic data

Entirely new — the baseline had no simulation capability at all.

- **Spectrum generator** — multi-line Gaussian profiles on a wavelength axis,
  with per-line FWHM, baseline offset and slope, SNR, and a seeded RNG.
  Identical inputs and seed yield identical output, and the complete generation
  parameters are recorded in the spectrum metadata.
- **Synthetic camera adapter** — fabricates *frames* that flow through the real
  grayscale and row-extraction path, so the pixel pipeline is exercised too.
- **Time-varying stream** with drift, rendered as a waterfall PNG.
- These are two distinct provenance identities — `synthetic-generator` versus
  `synthetic-camera` — recorded separately, because a synthesized spectrum and a
  synthesized frame validate different halves of the system.

## 9. Persistence and provenance

Baseline: `Spectrum-<timestamp>.csv` and `caldata.txt` dropped in the working
directory, with no metadata. Added:

- **Pluggable sink contract**, with CSV plus optional **SQLite** and
  **InfluxDB** backends, teed simultaneously.
- **SQLite as system of record** — spectrum arrays stored as explicitly
  little-endian `float64` BLOBs for portability between Pi and workstation,
  alongside calibration records and full per-capture provenance.
- **InfluxDB for scalar telemetry** — derived metrics over time, for Grafana.
  The two stores are deliberately *not* interchangeable; they hold different
  data because they are good at different things.
- **Locked core schema** — capture UUID, nanosecond timestamp, capture backend
  identity, and calibration fingerprint are fixed and cannot be overridden.
  Identity is stamped once before fan-out, so an InfluxDB point is always
  resolvable to its SQLite row.
- **Backend provenance as an integrity rule.** A calibration fitted on one
  backend is not valid on another; a store that cannot name its backend cannot
  be trusted to serve a wavelength axis.
- **Schema integrity on open** — the store stamps its core schema version and
  user-manifest fingerprint at creation and verifies both on every open,
  refusing to open on a mismatch rather than writing records that cannot later
  be interpreted.
- **User field manifest** — a declarative INI file adds typed columns to both
  stores at once, validated once, with core names reserved. Off by default; a
  blank path means core schema only.

## 10. Testing

Entirely new — the baseline had no tests.

- **328 tests** across unit, integration, regression and platform suites.
- **Golden regression tests** pin the baseline's exact numerical output and
  prove the extracted modules equivalent, so the migration is verifiable rather
  than asserted.
- **Ground-truth recovery tests** assert correctness against known synthetic
  input — peak positions, amplitude ordering, FWHM, SNR — rather than merely
  pinning whatever the baseline produced.
- Optional dependencies are skipped cleanly when absent.

## 11. Packaging

- Installable via `pip install -e .` with a `spectrometerv2` entry point.
- Optional extras: `usb`, `pi`, `plot`, `wavelet`, `gui`, `dev` — the core
  runtime needs only NumPy.
- Apache 2.0, matching upstream, with attribution preserved in `NOTICE` and
  `ATTRIBUTION.md`.

---

## Preserved unchanged

The following baseline behavior is intentionally identical and is pinned by
`tests/regression/`:

- Savitzky–Golay smoothing (vendored SciPy cookbook implementation)
- Peak detection (`peakIndexes`, vendored from *peakutils*, MIT)
- Wavelength calibration — 2nd-order polynomial fit for exactly three points,
  3rd-order for more
- Graticule tick generation at 10 nm and 50 nm intervals
- `wavelength_to_rgb` colour mapping across 380–750 nm
- Vertical-slice extraction — centre row with 3-row averaging

Les Wright's scientific work is the foundation; this project is a
re-implementation around it, not a replacement of it.

## Known gaps

- Absolute irradiance is out of scope — this instrument measures wavelength
  position only.
- Hardware test suite (`tests/hardware/`) is empty; hardware verification is
  manual.
- The full suite has been run on Linux/Python 3.10; Windows/Python 3.14
  confirmation is outstanding.
