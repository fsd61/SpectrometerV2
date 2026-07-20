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
- **Hardware-in-the-loop validation** — USB and Raspberry Pi adapters are
  implemented and contract-tested but not yet validated on real devices
  (Migration Plan Phase 6; Gate F).
- **GUI** — the OpenCV/graph/waterfall interface and keybindings (Migration Plan
  Phase 7); the extracted `ui/` package is still a stub.
- **Advanced analysis** — FFT, wavelet denoising, and simulated-annealing line
  fitting from the `Docs/reference/Patch_-_Wtx_+_SA` material, as optional dependency-gated
  features in `analysis/`.
