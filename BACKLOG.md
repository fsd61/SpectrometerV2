# Backlog — deferred / post-migration work

Parking lot for work intentionally deferred until the core migration
(Phases 0–8) is complete. Nothing here blocks the current plan.

## Telemetry, persistence & visualization (post-migration)

A dashboard/time-series story — **Grafana**, **InfluxDB**, and/or **SQL** — is
wanted but is a feature workstream of its own (new requirements, an ingestion
path, schema design, and a running service). Deferred until after Phase 8.

**Design seam in place, and the InfluxDB write path is now built:** the Data
Persistence layer is a pluggable `SpectrumSink` interface (`src/data/sinks.py`);
the default is `CsvSpectrumSink`. An optional, off-by-default
`InfluxDbSpectrumSink` (`src/data/influx.py`) now writes scalar features per
acquisition to InfluxDB **v1/v2/v3** over stdlib HTTP (no client dependency),
tagged `source` for measurement integrity; `MultiSink` tees it alongside CSV via
`build_sink()`. Remaining future backends — `SqlSpectrumSink`, a Grafana-friendly
exporter — are the same additive pattern, never touching the scientific core.
`Spectrum.metadata` carries what a time-series row needs (calibration, generation
params, timestamps, frame info). **Still out of scope / future:** the *read* side
(Grafana dashboards, or querying a v3 server, which would need `influxdb3-python`)
and formal `TEL-00x` requirements.

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
  ported from the original PySpectrometer2 patch material. SA is validated by
  seeded parametric recovery tests (known peaks + set SNR → recover within
  tolerance, across multiple seeds).
