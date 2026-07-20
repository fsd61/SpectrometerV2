# Changelog

All notable changes to **SpectrometerV2** are recorded here, one entry per
development step. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Requirement IDs (e.g. `CFG-001`) refer to the engineering documents in `Docs/`.

## [Unreleased] — branch `sprint-1-skeleton`

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
