# Changelog

All notable changes to **SpectrometerV2** are recorded here, one entry per
development step. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Requirement IDs (e.g. `CFG-001`) refer to the engineering documents in `Docs/`.

## [Unreleased] — branch `sprint-1-skeleton`

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
