# Changelog

All notable changes to **SpectrometerV2** are recorded here, one entry per
development step. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Requirement IDs (e.g. `CFG-001`) refer to the engineering documents in `Docs/`.

## [Unreleased] — branch `sprint-1-skeleton`

### 2026-07-23 — GUI Phase 7, milestone 7: offscreen tests + docs
**Added**
- Offscreen PySide6 widget tests (`tests/unit/test_qt_offscreen.py`, run under
  `QT_QPA_PLATFORM=offscreen`): action/shortcut registration for all 13 keys,
  menu/toolbar construction, graceful no-frame snapshot, toggle/param sync, and
  click-to-calibrate end-to-end (pick → snap → apply). They `importorskip`
  PySide6/pyqtgraph/pytest-qt, so they skip cleanly on a headless box and run
  wherever the `[gui]` extra is installed. `pytest-qt` added to the `dev` extra.
- An **Interactive GUI** section in `INSTALL.md`: the `[gui]` extra, launching
  `spectrometerv2 gui`, the 13-shortcut table, snapshot dir, and the
  click-to-calibrate workflow, plus how to run the offscreen GUI tests.

**Changed**
- Architecture doc: the Presentation Layer (GUI) status is now `[Implemented]`
  (was `[Planned]`). `BACKLOG.md` GUI entry refreshed to reflect M1–M6 done and
  M8 (OV9281 validation) as the remaining hardware step.

> M8 (on-hardware OV9281 validation) is deliberately untouched — the sensor is
> in hand but validation is a with-Frank step.

### 2026-07-23 — GUI Phase 7, milestone 6: click-to-calibrate
**Added**
- Click emission lines on the live plot to pick calibration points, then press
  `c` to fit and apply the wavelength calibration; `x` clears the picks. A
  checkable **Calibrate ▸ Pick points** mode (Ctrl+K) gates plot-click capture,
  and each click snaps to the nearest detected peak (within 12 px) before asking
  for the known wavelength.
- Qt-free core in `ui/live.py`: `CalibrationSession` (pick buffer with
  add/remove/clear, ≥3-point readiness, `fit`/`axis`/`save` delegating to the
  existing `calibration` package) and `snap_pixel_to_peak`. `LiveEngine` gains
  `set_calibration`/`clear_calibration`; it attaches the fitted axis to frames
  that arrive **uncalibrated** (the camera path) and never overwrites a frame
  that already carries wavelengths (synthetic ground truth stays ground truth).
- `SpectrumView` emits `plotClicked(x)`; the main window snaps, prompts for the
  wavelength, applies the fit to the running engine, and saves the points to the
  configured calibration file (baseline caldata format, CLI-interoperable).

**Fixed**
- `write_calibration_points` now writes its CRLFs verbatim (`newline=""`); on
  Windows the previous `\r\n` was being re-translated to `\r\r\n`, corrupting the
  caldata file on save (and failing the persistence round-trip on Windows).

_10 new tests (calibration session, peak snap, save round-trip, live-apply +
ground-truth protection). Sandbox suite 206 passed, 1 skipped._

### 2026-07-22 — GUI Phase 7 prep: wavelet / SA analysis parameters
**Added**
- Two flat config sections — `[wavelet]` (`wavelet` family, `level`) and
  `[annealing]` (`schedule`, `max_cycles`, `tol`, `n_components`,
  `bound_tightness`, `seed`, `lock_seed`) — holding the GUI-tunable defaults for
  the two heavy analyses. Kept flat (not `analysis.wavelet`) so
  `--set wavelet.key=value` overrides work; `config.ini.example` regenerated.
- Qt-free `ui/analysis_params.py`: `WaveletParams` and `SAFitParams`, mirroring
  the `LiveParams` pattern — curated choices, clamped adjusters, `from_config`
  builders, and `to_kwargs` that map exactly onto the `wavelet_transform` /
  `simulated_annealing` signatures. Only the *meaningful* knobs are exposed; the
  SA internals (`T0` auto-tune, step size, Markov factor, quench point) keep
  their good defaults and stay off the config surface. `n_components=0` → auto
  (derive from detected peaks), unlocked seed → fresh RNG, and
  `WaveletParams.effective_level()` reproduces PyWavelets' level clamp without
  importing pywt (honest effective-depth readout).
- 13 tests, including subset-of-signature guards so the params can't silently
  drift from the functions they feed. Suite 197 tests.

> Groundwork only — no Qt widgets yet. This is the testable core for a later
> advanced-analysis panel (fit-on-demand, seed recorded per fit).

### 2026-07-22 — GUI Phase 7, milestone 5: menu + toolbar, shortcuts, snapshot
**Added**
- A full **menu bar** (File / Calibrate / Analysis / View / Help) and a text
  **toolbar**, both built from a new Qt-free registry, plus the **13 original
  PySpectrometer2 keyboard shortcuts** — `h s c x m p o l i k u j q` — each bound
  to its action: snapshot (s), quit (q), apply/clear calibration (c/x), toggle
  hold-peaks (h) / measure (m) / pixel-positions (p), and nudge Savitzky-Golay
  order (o/l), peak min-distance (i/k), and threshold (u/j). A Help ▸ Keyboard
  shortcuts dialog (F1) lists them.
- **Snapshot / export** (key `s`) writes the current live spectrum through the
  existing `CsvSpectrumSink` (CSV + sidecar metadata), so GUI captures ride the
  same pluggable data seam as the CLI and future backends (BACKLOG.md). New
  `[gui] snapshot_dir` config key (default `snapshots`); `config.ini.example`
  regenerated.
- Qt-free core in `ui/live.py`: `LIVE_SHORTCUTS` registry + `ShortcutSpec`,
  `snapshot_spectrum()` / `snapshot_name()`, a real **hold-peaks** running
  element-wise maximum in `LiveEngine.step()`, and `LiveParams.pixel_mode`
  (mutually exclusive with `measure`, mirroring the original `recPixels`).
  `peak_readout_rows(..., force_pixel=)` reports pixel positions/widths in
  pixel-mode even when calibrated. The Qt widgets only render these.
- Menu/toolbar toggles, the control-dock sliders, and the shared `LiveParams`
  now stay in sync in both directions (dock edits update the toggles; keyboard
  changes refresh the dock).
- 10 new tests (pixel-mode exclusivity, hold-peaks accumulation/reset, registry
  completeness + shape, snapshot round-trip through the sink, pixel-mode
  readout). Suite 184 tests.

> Click-to-*pick* calibration points is milestone 6; the `c`/`x` actions and a
> pending-points buffer exist now, and M6 wires the plot clicks into them.

### 2026-07-21 — GUI Phase 7, milestone 4.5: synthetic source panel
**Added**
- A live **signal-generator** dock ("Synthetic source", synthetic mode only):
  global SNR, baseline, sample interval, seed, wavelength range, and a drift
  toggle, plus an add/remove peak table with per-peak wavelength, amplitude, and
  FWHM. Every edit rebuilds the spec and swaps it into the running frame source,
  so the plot/waterfall/readouts update on the next frame. Turns synthetic mode
  into a live ground-truth test bench (set a peak's FWHM/SNR, watch the readout
  recover it).
- Measurement integrity: the dock exists **only** when the backend is synthetic,
  is labeled "[SIMULATED]", and the window title gains a `[SIMULATED]` marker
  while it is active. Snapshots already carry `source=synthetic` in metadata.
- Qt-free core in `ui/live.py`: `SyntheticPeak`, `build_synthetic_spec()`,
  `spec_to_peaks()`, and live `set_spec()` / `set_drift()` on
  `SyntheticFrameSource`. The synthetic panel is tabbed with the analysis
  Controls dock; both are reopenable from the View menu.
- 5 new tests including live ground-truth recovery (set peaks → pipeline
  recovers their centers) and live spec swapping. Suite 174 tests.

### 2026-07-21 — GUI Phase 7, milestone 4: control dock + readouts
**Added**
- `ui/qt/controls.py`: a right-hand dock with live sliders for smoothing (savgol
  order), peak min-distance, and threshold, plus a "measure FWHM/SNR" toggle.
  Sliders mutate the shared `LiveParams` in place, so changes take effect on the
  next captured frame. A peak table shows position (nm or pixel), intensity,
  FWHM, and SNR, refreshed every frame.
- Qt-free `peak_readout_rows()` + `PeakRow` in `ui/live.py` build the table rows
  (calibrated vs pixel positions, nm vs px FWHM), so the formatting logic is
  unit-tested without a display. The GUI now defaults to `measure=True`.
- 3 new readout tests (calibrated+measured, no-measure, uncalibrated pixel
  positions). Suite 169 tests.

### 2026-07-21 — GUI Phase 7, milestone 3: live waterfall
**Added**
- Qt-free `WaterfallBuffer` in `ui/live.py`: a fixed-height scrolling image of
  recent spectra (rows = time, newest first), width locked on first push,
  negatives floored to match the trace. Unit-tested without a display.
- `ui/qt/waterfall_view.py`: a pyqtgraph image widget (viridis, newest at top)
  painting the buffer. The main window now stacks the spectrum plot over the
  waterfall in a vertical splitter and pushes each frame to both.
- New `[gui].waterfall_frames` config key (history depth); `config.ini.example`
  regenerated.
- 7 new buffer tests (scroll order, eviction, width lock/clip/pad, flooring,
  clear). Suite 166 tests.

### 2026-07-21 — GUI Phase 7, milestone 2: live spectrum plot
**Added**
- Qt-free live core in `ui/live.py`: a `FrameSource` protocol with
  `SyntheticFrameSource` (advances the reproducible synthetic stream) and
  `CameraFrameSource` (drives a camera adapter via the acquisition service),
  `build_frame_source(config)` (synthetic by default, else builds/initializes the
  configured camera), and `LiveEngine.step()` which pulls a frame and runs it
  through the existing analysis pipeline. All unit-tested without a display.
- `ui/qt/spectrum_view.py`: a pyqtgraph live plot (smoothed trace + peak markers,
  wavelength or pixel axis). `ui/qt/controller.py`: a `QThread` that steps the
  engine off the UI thread and emits each analyzed frame via Qt signals. The main
  window now hosts the plot, starts capture, and shows sample/peak counts in the
  status bar; it releases the source on close.
- New `[gui]` config section with `fps` (target live refresh rate);
  `config.ini.example` regenerated.
- 5 new engine/source tests (build, step→peaks, stream advance, params→measure,
  camera-adapter path). Suite 159 tests.

### 2026-07-21 — GUI Phase 7, milestone 1: app skeleton + `gui` command
**Added**
- `[gui]` optional extra (PySide6 + pyqtgraph).
- `ui/live.py`: a **Qt-free** live-view core. `LiveParams` mirrors the original
  tool's live controls (savgol order, peak min-distance, threshold, hold-peaks,
  measure) with the same bounds, as pure testable adjusters. All GUI logic will
  live here so it can be unit-tested without a display; the Qt widgets only
  render what it produces.
- `ui/qt/` PySide6 skeleton: `app.run_gui()` + a titled `MainWindow` (placeholder
  central widget + status bar). This subpackage is the only place PySide6 is
  imported.
- New `spectrometerv2 gui` subcommand. It imports the Qt layer lazily and, if the
  `[gui]` extra is missing, prints an actionable message (`pip install -e .[gui]`)
  and exits non-zero — same pattern as the camera adapters.
- 7 new tests (LiveParams clamping/toggles/kwargs; `gui` parsing; graceful
  fallback forced independent of environment). Suite 154 tests.

> Note: PySide6 is intentionally **not** in the `dev` extra — plain `pytest`
> must not require Qt's system GL libraries. The offscreen widget tests
> (milestone 7) will `importorskip` so they skip cleanly where Qt can't load.

### 2026-07-21 — Advanced analysis: simulated-annealing line fitting
**Added**
- `analysis/annealing.py`: `simulated_annealing()` — a global optimizer based on
  DiGennaro & Cowburn (J. Magn. Reson. 96, 582-588, 1992), with auto-tuned T0,
  component-scaled Markov chains, a quench point, and threshold termination.
  NumPy-only (no new dependency). Returns a typed `AnnealingResult`.
- Convenience helpers `gaussian_sum()` and `sum_of_squares_objective()` for the
  common "fit a sum of Gaussians to a spectrum" case.
- Ported from `Docs/reference/Patch_-_Wtx_+_SA/`. Modernized: diagnostics go
  through `logging` (not `print`); a local seeded RNG replaces global
  `random`/`numpy` state, so seeded runs are reproducible and leak no state.
- 8 new tests, including **parametric recovery** (known peaks at a set SNR →
  recover centers/amplitudes within tolerance, across multiple seeds) and a
  reproducibility check. This completes the advanced-analysis backlog item.
  Suite 147 tests.

### 2026-07-21 — Advanced analysis: FFT + wavelet transforms
**Added**
- `analysis/transforms.py`: `fft_spectrum()` (one-sided FFT magnitude spectrum,
  NumPy-only, always available) and `wavelet_transform()` (discrete wavelet
  decomposition via PyWavelets). Both return typed result dataclasses
  (`FftResult`, `WaveletResult`) and are exported from `analysis`.
- PyWavelets is an **optional** dependency behind the new `[wavelet]` extra and
  is imported lazily with an actionable install message; FFT needs nothing
  beyond NumPy.
- Ported from `Docs/reference/Patch_-_Wtx_+_SA/`. Simulated-annealing line
  fitting from the same material remains on the backlog (stochastic — needs
  seeded, tolerance-based tests).
- 6 new unit tests (known-frequency recovery, DC component, wavelet
  reconstruction, level clamping, missing-dependency message). Suite 139 tests.

**Docs**
- INSTALL.md: added a Raspberry Pi hardware note — Pi 4 on 64-bit OS recommended
  (prebuilt aarch64 wheels); Pi 3B works via the 32-bit path.

### 2026-07-21 — Config values: case-insensitive choices + whitespace-tolerant
**Fixed**
- Choice values are now **case-insensitive** and normalized to the schema's
  canonical spelling (e.g. `AUTO`/`AuTo` → `auto`, `info` → `INFO`). Previously
  only the exact lower/upper form in the schema was accepted.
- Surrounding **whitespace** in string and path values is stripped (from both
  config files and `--set` overrides). Int/float/bool already tolerated it.
- Genuinely invalid choices are still rejected with the same clear error. Suite
  133 tests.

### 2026-07-21 — Fix camera backend: drop 'none', platform-aware auto, clearer errors
**Changed / Fixed**
- Removed `none` from the camera backend options (back to
  **`auto | usb | csi | synthetic`**; `picamera2` alias kept).
- **`auto` is now platform-aware**: on a Raspberry Pi it prefers the CSI camera
  (picamera2) and only falls back to USB if picamera2 is unavailable; off a Pi it
  uses USB. Previously it chose purely by whether `picamera2` imported, which
  could send a Pi down the USB path.
- Missing-library errors are now **actionable**: the USB path explains how to
  install OpenCV (`pip install -e .[usb]`, or `apt install python3-opencv` on a
  Pi); the CSI path points to `apt install python3-picamera2` + a
  `--system-site-packages` venv.
- `scripts/setup_pi.sh` now also installs `python3-opencv`. Suite 131 tests.

### 2026-07-21 — Camera backends: rename picamera2 → csi, add none
**Changed**
- Camera `backend` options are now **`auto | usb | csi | synthetic | none`**.
  `csi` names the Raspberry Pi ribbon interface (clearer and driver-agnostic);
  `picamera2` is still accepted as a silent alias. Platform auto-detection now
  recommends `csi` on a Pi.
- `none` = no camera: `run` refuses with guidance, `test-camera` /
  `verify-hardware` report it as disabled, and `analyze` / `generate-synthetic`
  are unaffected. `synthetic` keeps its explicit, clearly-labelled meaning (kept
  deliberately, not folded into `none`).
- Suite 133 tests.

### 2026-07-21 — Project-local config + verbose init-config
**Changed**
- Configuration is now **project-local and self-contained**: the app looks for
  `config/config.ini`, resolved from the project root (found by walking up for
  `pyproject.toml`, so it works from any subdirectory). The `~/.config` (XDG)
  location is gone — everything lives in the movable project directory.
- `init-config` is now **verbose**: it narrates each step (project root, config
  directory, platform, suggested camera backend, what it wrote) and ends with a
  short "settings you'll most likely want to review" list, so first-run is
  self-explanatory without interactive prompts.
- Alternate setups are explicit files in `config/` (e.g. `config/lab.ini`),
  selected with `--config config/lab.ini`.
- `src/config/generate.py`: `find_project_root`, `config_path`, `config_dir`;
  updated tests (project-local discovery) and README. Suite 131 tests.

### 2026-07-19 — Single-file configuration (init-config + auto-discovery)
**Added**
- `init-config` command — writes a fully-commented
  `~/.config/spectrometerv2/config.ini`, generated from the schema so the
  documentation and defaults are always current (`--force` to overwrite).
- **Config auto-discovery** — the app loads `./spectrometerv2.ini` or
  `~/.config/spectrometerv2/config.ini` automatically; `--config` still
  overrides. No `--config` needed for normal use.
- `src/config/generate.py` (`render_ini`, `discover_config_path`,
  `user_config_path`); tests plus an XDG-isolated `conftest.py`.

**Changed**
- Renamed `config/default.ini` → `config/config.ini.example` (a browsable copy,
  regenerated from the schema). README/INSTALL updated to the single-file model.
  Suite now **132 tests**.

### 2026-07-19 — One-command Raspberry Pi setup
**Added**
- `scripts/setup_pi.sh` — turnkey Pi install: apt-installs the camera stack plus
  NumPy/matplotlib/OpenBLAS, creates a `--system-site-packages` venv (so pip uses
  the Pi-built NumPy and the `libopenblas.so.0` issue never arises), installs
  SpectrometerV2, and verifies `--version`. Idempotent.

**Changed**
- `INSTALL.md`: the Raspberry Pi path now leads with `bash scripts/setup_pi.sh`
  (manual steps kept as the equivalent); noted the wrinkle is 32-bit-only.

### 2026-07-19 — Docs: Raspberry Pi NumPy/OpenBLAS install note
**Changed**
- `INSTALL.md`: document the `libopenblas.so.0` gotcha on Raspberry Pi (pip's
  NumPy wheel needs the system OpenBLAS library). Recommend installing
  `python3-numpy` + `libopenblas0` via apt and using a `--system-site-packages`
  venv, with a fallback if pip's NumPy is already in place. (No code change — the
  app itself was fine; this was an environment prerequisite.)

### 2026-07-19 — Remove configuration profiles
**Removed**
- The configuration **profiles** feature: `config/profiles/lab.ini` and
  `config/profiles/synthetic-ci.ini`, the `--profile` flag, and the overlay
  logic in `config/loader.py`. Unnecessary for a single-user instrument; the
  `--set section.key=value` overrides cover the remaining need.

**Changed**
- Requirements → **Rev 1.8**: CFG-003 (multiple configuration profiles) marked
  *Withdrawn*.
- README and `config/default.ini` de-referenced profiles. Suite now 126 tests.

### 2026-07-19 — Camera auto-detect with explicit no-camera policy
**Changed**
- Default `camera.backend` → **`auto`** (set in `schema.py`, the effective
  default; mirrored in `config/default.ini`). `auto` picks the Raspberry Pi
  camera or an available USB camera.

**Added**
- `camera.on_missing` option (`prompt` | `error` | `synthetic`) governing what
  `auto` does when **no camera is found**:
  - `prompt` (default) — asks in an interactive terminal (defaults to No/exit);
    **degrades to `error` when non-interactive** so headless/automated runs never
    hang.
  - `error` — exits with actionable guidance.
  - `synthetic` — falls back to simulated data with a loud banner.
  Simulated runs are flagged in the output (`[SIMULATED]`) and in metadata
  (`source: synthetic`) so they can never be mistaken for real measurements.
- `src/app/hardware.py` `select_camera()` encapsulating the policy (prompt
  injectable for testing). Unit tests for every policy + the headless
  degradation. Suite now **127 tests**.

### 2026-07-19 — Declutter: patch material moved to Docs/reference/
**Changed**
- Relocated `Patch_-_Vertical_Slice/` and `Patch_-_Wtx_+_SA/` from the repo root
  into `Docs/reference/` — historical, reference-only material not used by the
  project (the Wtx+SA advanced-analysis code is earmarked in `BACKLOG.md`).
  Updated README, BACKLOG, and the legacy inventory to the new paths.

### 2026-07-19 — Licensing & attribution (Apache-2.0)
**Added**
- `LICENSE` — Apache License 2.0 (matches the upstream project).
- `NOTICE` — required attribution: copyright Frank DiGennaro; derived from
  PySpectrometer2 by Les Wright (Apache-2.0); vendored algorithm credits
  (SciPy Savitzky-Golay, BSD-3-Clause; peakutils peak detection, MIT).
- `ATTRIBUTION.md` — provenance: behavior preserved and golden-tested, the
  implementation essentially new (~100% of the science retained, ~98% of the
  code new), and third-party algorithm credits.

**Changed**
- `pyproject.toml` license → **Apache-2.0** (replacing an early GPL placeholder;
  now matches upstream).
- README: acknowledgements point to `ATTRIBUTION.md`/`NOTICE`; added a License
  section.

### 2026-07-19 — Streaming synthetic source + visualization
**Added**
- `src/synthetic/stream.py` — `SyntheticStream`: a reproducible, time-varying
  scene (line drift + amplitude jitter + per-frame seeded noise) yielding
  evolving `Spectrum` frames — the substrate for live/waterfall development and
  streamed storage, no hardware required.
- `src/ui/plotting.py` — `render_spectrum` (intensity trace + peak markers) and
  `render_waterfall` (stacked spectra over time) to PNG via matplotlib
  (lazy-imported; new `[plot]` extra), so importing the package never needs it.
- CLI: `--plot` saves a spectrum PNG on `run` / `generate-synthetic` / `analyze`;
  new `stream` command plays a synthetic stream and renders a waterfall PNG
  (`--frames N`).
- Unit tests (stream, plotting) and CLI tests; `[plot]` extra in pyproject.
  Suite now **121 tests**.

### 2026-07-16 — Docs synced for Phase 8 groundwork
**Changed**
- Requirements → **Rev 1.7** (TEST-001 and ACC-001 → *In Progress*).
- Migration Plan → **Rev 1.8** (Phase 8 and Gate F → *In Progress*).
- Architecture → **Rev 1.9** (platform acceptance tests → *In Progress*).
- README Status updated (112 tests, installable).

### 2026-07-16 — Phase 8 groundwork: packaging, install docs, acceptance test
**Added**
- `INSTALL.md` — Linux / Windows / Raspberry Pi prerequisites and quickstart
  (Migration Plan Phase 8: document installation and platform prerequisites).
- `tests/platform/test_platform_acceptance.py` — full-stack smoke on the current
  platform (detection, synthetic acquisition → analysis, generate → persist →
  reload → analyze, CLI run). Suite now **112 tests**.

**Changed**
- `pyproject.toml`: declare **numpy** as a runtime dependency; add `[usb]`
  (opencv-python) and `[pi]` (picamera2) optional extras. Verified
  `pip install -e .` builds and the `spectrometerv2` console script runs the
  full pipeline end-to-end.

### 2026-07-16 — Docs synced for Phase 6
**Changed**
- Requirements → **Rev 1.6** (CLI-004, ERR-001, PLAT-004, DATA-002 →
  *Implemented*; PLAT-001/002/003/007, DATA-001 → *In Progress*).
- Migration Plan → **Rev 1.7** (Phase 6 → *In Progress* — headless Linux path
  validated; Windows/Pi hardware pending).
- Architecture → **Rev 1.8** (Application Core and Data Persistence →
  *Implemented*).
- README Status updated (108 tests).

### 2026-07-16 — Phase 6: platform detection + remaining diagnostics
**Added**
- `src/platforms/detect.py` — `detect_platform()` / `recommended_camera_backend()`
  (Raspberry Pi detection; uses the now-unshadowed stdlib `platform`).
- `src/calibration/persistence.py` — `load_calibration_points` /
  `write_calibration_points` (baseline `caldata.txt` format).
- CLI `verify-hardware` (platform + camera report) and `check-calibration`
  (fit report: point count, order, R², wavelength range) — completing the
  CLI-004 diagnostic set (test-camera, verify-hardware, check-calibration,
  validate-config, generate-synthetic, analyze).
- Unit tests (platforms, calibration persistence) and CLI tests. Suite now
  **108 tests**.

### 2026-07-16 — Application core wired end-to-end + pluggable persistence
**Added**
- `src/data/sinks.py` — `SpectrumSink` interface with `CsvSpectrumSink`
  (CSV + sidecar metadata JSON), `NullSink`, and `read_csv_spectrum`. Built so
  InfluxDB / SQL / Grafana backends are future implementations of the same
  interface (DATA-001/002; see `BACKLOG.md`).
- `src/app/commands.py` + wired CLI: `run`, `test-camera`, `generate-synthetic`,
  and `analyze` now work end-to-end (config → camera factory → acquisition →
  analysis → sink); added `--output` / `--input`.
- `BACKLOG.md` capturing deferred features (Grafana/InfluxDB/SQL) and the
  pluggable-sink design intent.
- Unit tests for sinks and integration tests driving the CLI (synthetic backend,
  graceful USB failure without hardware). Suite now **98 tests**.

The application now runs headless on Linux — exercising config, camera
discovery, acquisition, analysis, logging, persistence, and synthetic generation
(Migration Plan Phase 6, Linux path). Docs will be synced at Phase 6 completion.

### 2026-07-16 — Docs synced for Phase 5
**Changed**
- Requirements → **Rev 1.5** (HW-001…004 and PLAT-005 → *Implemented*).
- Migration Plan → **Rev 1.6** (Gate E → *In Progress*).
- Architecture → **Rev 1.7** (Camera Abstraction Layer and Acquisition Service →
  *Implemented*; camera-contract tests → *Implemented*).
- README Status updated (86 tests).

### 2026-07-16 — Phase 5: camera abstraction + acquisition
**Added**
- `src/cameras/`: `SyntheticCameraAdapter` (hardware-free; frames encode a
  pixel-space spectrum), `UsbCameraAdapter` (lazy `cv2`, cross-platform
  open-by-index — fixes the baseline's Linux-only V4L path, PLAT-002),
  `Picamera2Adapter` (lazy import, PLAT-005), and a `create_camera` /
  `create_camera_from_config` factory selecting by backend.
- `src/acquisition/service.py`: `acquire_spectrum(camera)` → `extract_spectrum`
  with frame metadata; depends only on the camera contract.
- Tests: synthetic-camera unit, camera-contract conformance for all three
  adapters, factory, and an integration test (synthetic camera → acquire →
  extract → analyze recovers the lines, hardware-free). Suite now **86 tests**.

### 2026-07-16 — Docs synced for Phase 4
**Changed**
- Requirements → **Rev 1.4** (SYN-001…006, 008, 009 *Implemented*; SYN-007
  *In Progress* — Gaussian done, Lorentzian/Voigt future).
- Migration Plan → **Rev 1.5** (Phase 4 and Gate D → *In Progress*).
- Architecture → **Rev 1.6** (Synthetic Spectrum Generator → *Implemented*).
- README Status updated (70 tests).

### 2026-07-16 — Phase 4: synthetic spectrum generator
**Added**
- `src/synthetic/generator.py` — production generator (SYN-001…009): wavelength
  axis (min/max/interval), multi-line Gaussian with global or per-line FWHM,
  amplitudes, baseline level + slope, SNR-based deterministic noise (seed), and
  full generation metadata; outputs the shared `Spectrum` and flows through the
  same `analyze` pipeline (SYN-008). Lorentzian/Voigt raise `NotImplementedError`
  (SYN-007, future). `SyntheticSpectrumSpec.from_config` ties into `[synthetic]`.
- Unit tests (reproducibility, axis, baseline/slope, per-line FWHM, SNR,
  metadata, error cases) and an integration test (generate → analyze recovers
  wavelengths, FWHM, and SNR).

**Changed**
- `analysis.gaussian_fit` now fits only the line *core* (`min_fraction`) for
  accurate narrow-line FWHM.
- Suite now **70 tests**.

### 2026-07-16 — Phase 3: FWHM, SNR, Gaussian fit (scientific core extracted)
**Added**
- `src/analysis/measurements.py` — `half_max_fwhm`, `gaussian_fit`
  (dependency-free log-parabola), `estimate_noise` (Savitzky–Golay-residual
  MAD), and `estimate_snr`. New capability beyond the baseline (TEST-002:
  FWHM/amplitude/SNR recovery).
- Pipeline `analyze(measure=True)` adds per-peak FWHM (px and nm), amplitude,
  and SNR, plus `SpectralAnalysis.noise`.
- Unit tests for the measurements and a pipeline measurement test. Suite now
  **59 tests**.

**Changed**
- Architecture → **Rev 1.5**: Spectrum Extraction and Scientific Analysis
  components → *Implemented*.
- README: Status now reflects the extracted scientific core.

### 2026-07-16 — Phase 3: spectrum extraction + end-to-end pipeline
**Added**
- `src/processing/extraction.py` — `extract_spectrum` / `extract_intensity` /
  `to_grayscale`, porting the baseline crop → 3-row-mean → uint8 intensity step
  into a platform-neutral function producing the shared `Spectrum` (center row =
  `H // 2`, exact 3-row mean with uint8 truncation).
- `src/analysis/pipeline.py` — `analyze()`: Savitzky–Golay smoothing + peak
  detection + optional pixel→wavelength mapping, returning `Peak(pixel,
  intensity, wavelength)`.
- Unit tests for extraction and an integration test (frame → extract →
  calibrate → analyze recovers all four reference peaks with correct
  wavelengths). Suite now **52 tests**.

### 2026-07-16 — Phase 3: first scientific-core extraction
**Added**
- `src/analysis/smoothing.py` (`savitzky_golay`), `src/analysis/peaks.py`
  (`peak_indexes`), and `src/calibration/wavelength.py` (polynomial calibration)
  — extracted from the baseline and proven equivalent to `golden/*.json`
  (Savitzky–Golay max diff 5e-9; peak indices and calibration exact).
- `tests/regression/test_extracted_equivalence.py` (Gate C equivalence) plus
  unit tests for the analysis and calibration modules. Suite now **42 tests**.

**Changed**
- Migration Plan → **Rev 1.4**: Phase 3 and Gate C → *In Progress*; first-sprint
  step 7 → *In Progress*.
- Architecture → **Rev 1.4**: Scientific Analysis and Calibration Service →
  *In Progress*.
- README: de-pinned the engineering-document version references.

### 2026-07-16 — Sync engineering docs to progress (Rev 1.3)
**Changed**
- Bumped the three engineering documents to **Rev 1.3** (history rows) and
  renamed them to `..._Rev_1.3.docx`.
- Migration Plan: Phase 1 → *In Progress*; first-sprint steps 2 (inventory) and
  6 (golden regression suite) → *Implemented*.
- Requirements: TEST-002 (synthetic verification) → *In Progress*.
- Architecture: added status to the Testing Architecture section — unit,
  golden-data, and synthetic-data tests *Implemented*; camera-contract,
  platform-acceptance, and hardware-in-the-loop *Planned*.
- README: reference Rev 1.3 and note the golden regression suite.

### 2026-07-16 — Phase 1: golden regression suite
**Added**
- `tests/regression/` — characterization + ground-truth suite that pins the
  proven baseline scientific behavior before the core is extracted:
  - `_baseline.py` loads the original `specFunctions.py` and provides a
    deterministic (seeded, version-stable) multi-Gaussian spectrum generator.
  - `golden/*.json` snapshots: Savitzky–Golay output, peak indices,
    wavelength→RGB map, 3- and 4-point calibration, and graticule.
  - `test_baseline_characterization.py` (5 tests) re-runs the baseline and
    asserts equivalence to the golden snapshots (within tolerance).
  - `test_synthetic_recovery.py` (4 tests) verifies peak-center recovery,
    amplitude ordering, an FWHM self-check, and an SNR sanity relationship —
    the template the migrated `analysis` module must satisfy (TEST-002).
  - `generate_golden.py` + `README.md` documenting the regenerate/verify flow.
- Test suite now **25 tests** (was 16). Advances Migration Plan Phase 1 and lays
  the groundwork for Gate C (scientific core matches golden data).

### 2026-07-16 — Legacy feature inventory
**Added**
- `Docs/Legacy_Feature_Inventory.md` — catalog of the baseline PySpectrometer2
  code: source files, dependencies, CLI, camera acquisition, processing
  pipeline, keybindings, output formats, hard-coded parameters, known
  limitations, and a mapping to the target modules; plus the Wtx+SA patch's
  optional advanced analysis (FFT, wavelets, simulated annealing, plotting).
  Supports Migration Plan Phase 0 / the first-sprint inventory step.

### 2026-07-16 — Rebrand to SpectrometerV2 + platform package rename
**Changed**
- Docs: replaced the remaining project-name uses of "PySpectrometer2" with
  "SpectrometerV2" across all three engineering documents (titles, `Project:`,
  prose); corrected the Architecture §7 package paths to the flattened `src/`
  layout; renamed the files to `SpectrometerV2_*_Rev_1.2.docx`.
- Renamed the `src/platform/` package to `src/platforms/` so it no longer
  shadows the standard-library `platform` module; updated README, Architecture
  §7, and the `pyproject.toml` note.

**Fixed**
- `import platform` resolves to the standard library again (verified). 16 tests pass.

### 2026-07-16 — Engineering docs: implementation-status annotations (Rev 1.2)
**Changed**
- Bumped the three engineering documents to **Rev 1.2** (revision block + history
  row) and renamed the files to `..._Rev_1.2.docx`.
- Requirements: added inline `[Implemented]` / `[In Progress]` / `[Planned]`
  tags to all 40 requirements, plus a status legend.
- Migration Plan: tagged the 9 phases, 7 gates, and the 7 first-sprint checklist
  items.
- Architecture: tagged the 11 component-model entries and added a note on the
  implemented flattened `src/` layout.

**Added**
- `CHANGELOG.md` (this file), maintained per development step.

### 2026-07-16 — Repository organization (`cc48382`)
**Changed**
- Moved the three engineering documents and `Spectrometer_-_Grafana.png` into
  `Docs/`; README points at `Docs/`.

**Added**
- `Docs/Journal.Mag.Res.96.pdf` (reference paper).

### 2026-07-15 — Project rename & package flatten (`2991250`)
**Changed**
- Flattened `src/pyspectrometer2/*` directly into `src/` (no wrapper package);
  `app/` carries `__version__` and a `__main__` (`python -m app`).
- Renamed identifiers `pyspectrometer2` → `spectrometerv2` (CLI command, logger,
  log filename, console entry point); display name → **SpectrometerV2**.
- Replaced spaces with underscores in all tracked file/directory names.
- Updated `pyproject.toml` and README; added upstream credit to Les Wright's
  PySpectrometer2.

**Known issue**
- Flat layout: top-level `platform` shadows the standard-library module when
  `src` is on `sys.path`. Harmless in current source/test runs; to be resolved
  before installable packaging.

### 2026-07-15 — Sprint 1 skeleton (`abb8341`)
**Added**
- Package tree under `src/` per Architecture §7 (app, config, platform, cameras,
  acquisition, processing, calibration, analysis, synthetic, data, ui) + a
  five-way `tests/` tree.
- Configuration service — documented INI schema, profiles, `--set` overrides,
  and validation with graceful termination (CFG-001…CFG-006).
- Logging service — structured rotating file logs + optional console
  (LOG-001, LOG-002, ERR-002).
- CLI entry point (CLI-001…CLI-003; CLI-004 diagnostics stubbed).
- Shared `Spectrum` data object, camera contract + adapter stubs, and a
  synthetic-generator spec stub.
- `pyproject.toml`, `.gitignore`, README. 16 unit tests passing.
- Baseline tag `baseline-v1.0`; feature branch `sprint-1-skeleton`.

### 2026-07-15 — Baseline (`bca9f67`, `main`)
- Initial commit: upstream PySpectrometer2 (Les Wright), preserved patch
  material, and the Rev 1.1 engineering documents.

---
*Maintained by the SpectrometerV2 project. Update this file with every step.*
