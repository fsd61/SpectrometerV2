# Backlog — deferred / post-migration work

Parking lot for work intentionally deferred until the core migration
(Phases 0–8) is complete. Nothing here blocks the current plan.

## Telemetry, persistence & visualization — **write side DONE** (2026-08-10)

The **write side is complete**: both stores, the locked core schema, and the
user extension mechanism. See the CHANGELOG entry for 2026-08-10.

- `data/schema_core.py` — the locked core (capture identity, backend
  provenance, calibration fingerprint). Closed to extension.
- `data/sqlite.py` — the queryable system of record: spectrum arrays (BLOB, one
  row per capture), calibration records, provenance. Off by default.
- `data/influx.py` — scalar telemetry for Grafana, v1/v2/v3, stdlib-only.
- `data/user_schema.py` — declarative INI manifest; one declaration yields both
  a typed SQLite column and an InfluxDB field/tag. Tags require an enumerated
  `allowed` list, so tag cardinality cannot run away.
- `data/factory.py` — assembles the sinks and assigns capture identity once, so
  an InfluxDB point resolves to its SQLite row via `capture_uuid`.

The two stores are **complementary, not interchangeable**: SQLite holds what
must be kept and re-examined, InfluxDB holds what must be watched over time.
Forcing a 1280-sample spectrum into a time-series database is the thing this
split exists to avoid.

**Still out of scope / future:**

- The **read side** — Grafana dashboards, or querying a v3 server (needs
  `influxdb3-python`).
- Formal `TEL-00x` requirement IDs in the Requirements document, and a
  Persistence/Export section in the Architecture document. The design decisions
  are recorded in the module docstrings and the CHANGELOG in the meantime.
- An `export` command to expand BLOB spectra to long-form CSV/Parquet for
  external tools.
- Raw *frame* archival. Only the extracted 1-D spectrum is persisted today; the
  ablation-testing plan ("all stages read from immutable raw data") will
  eventually want the frames themselves indexed alongside.

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
