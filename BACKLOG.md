# Backlog — deferred / post-migration work

Parking lot for work intentionally deferred until the core migration
(Phases 0–8) is complete. Nothing here blocks the current plan.

## Telemetry, persistence & visualization (post-migration)

A dashboard/time-series story — **Grafana**, **InfluxDB**, and/or **SQL** — is
wanted but is a feature workstream of its own (new requirements, an ingestion
path, schema design, and a running service). Deferred until after Phase 8.

**Design seam already in place:** the Data Persistence layer is built around a
pluggable `SpectrumSink` interface (`src/data/sinks.py`). Today the default is
`CsvSpectrumSink` (CSV + sidecar metadata JSON). Future backends —
`InfluxDbSpectrumSink`, `SqlSpectrumSink`, a Grafana-friendly exporter — are just
additional implementations of the same interface, so adding them is *additive*
and never touches the scientific core (support without coupling).
`Spectrum.metadata` already carries what a time-series row needs (calibration,
generation params, timestamps, frame info).

When picked up, add explicit requirements (e.g. TEL-00x) to the Requirements
document and a Presentation/Export section to the Architecture document.

## Other deferred items

- **Synthetic line profiles** — Lorentzian and Voigt (SYN-007 extension points;
  Gaussian is implemented).
- **Legacy path removal** — retire `Original_Pyspectrometer2/specFunctions.py`
  usage only after full equivalence is demonstrated (Migration Plan Gate G).
- **Hardware-in-the-loop validation** — the **USB adapter is now validated on a
  real device** (Arducam USB OV9281, native 1280×800). The Raspberry Pi (CSI/
  picamera2) adapter is still implemented and contract-tested but not yet run on
  real hardware (Migration Plan Phase 6; Gate F).
- **GUI** — **largely done** (Migration Plan Phase 7). The PySide6 desktop app
  (`ui/qt/`, over the Qt-free `ui/live.py` core) has the live spectrum plot,
  scrolling waterfall, control dock + FWHM/SNR readouts, synthetic
  signal-generator panel, a full menu + toolbar with the 13 original keyboard
  shortcuts, snapshot/export through the data sink, and click-to-calibrate
  (M1–M6). M7 (offscreen widget tests + docs) done. **M8 software validated on a
  real USB OV9281** (opens at native 1280×800, `run` acquires end-to-end, live GUI
  renders on real frames); the remaining M8 step is the **on-bench argon-line
  calibration** (FS-2 doublet at 810.4/811.5 nm) — optical work, not software.
  The wavelet/SA fit *panel* is not built yet, though its Qt-free parameter core
  (`ui/analysis_params.py`) and config sections are in place.
- **Advanced analysis** — **done.** FFT and wavelet decomposition
  (`analysis/transforms.py`; wavelet gated behind the `[wavelet]` extra) and
  simulated-annealing line fitting (`analysis/annealing.py`, NumPy-only) are all
  ported from the `Docs/reference/Patch_-_Wtx_+_SA` material. SA is validated by
  seeded parametric recovery tests (known peaks + set SNR → recover within
  tolerance, across multiple seeds).
