# PySpectrometer2

Modular, cross-platform scientific spectrometer application.

> *Think like a physicist. Build like an engineer.*

This is the modernization of PySpectrometer2 into a maintainable architecture
with **one platform-neutral scientific core** and all OS/camera specifics behind
adapters. Linux, Windows, and Raspberry Pi are equal first-class platforms.
See the Rev 1.1 engineering documents in the repository root for the governing
Requirements, Architecture & Design, and Migration Plan.

## Repository layout

```
src/pyspectrometer2/     Application package
  app/          startup, CLI, orchestration
  config/       INI schema, validation, profiles      (CFG-*)
  platform/     platform-specific services            (PLAT-*)
  cameras/      camera contract + adapters (USB, Pi)   (HW-*)
  acquisition/  frame capture + acquisition metadata
  processing/   spectrum extraction + shared Spectrum object
  calibration/  wavelength calibration
  analysis/     peak detection, fitting, FWHM, SNR
  synthetic/    reproducible synthetic spectra         (SYN-*)
  data/         persistence + metadata                 (DATA-*)
  ui/           GUI + plotting
config/         default.ini + profiles/                (externalized config)
tests/          unit / integration / regression / hardware / platform
Original Pyspectrometer2/   Preserved upstream baseline (tag: baseline-v1.0)
Patch - *                   Preserved in-progress patch material
```

## Status

Sprint 1 skeleton. Working today: configuration service and logging service,
wired into a CLI. Scientific modules, camera adapters, and the synthetic
generator are stubs to be filled in per the Migration Plan phases.

## Usage

```bash
pip install -e .[dev]

# Validate configuration (CLI-004)
pyspectrometer2 --config config/default.ini validate-config

# Print the documented configuration schema (CFG-004)
pyspectrometer2 describe-config

# Overlay a profile and override a value at the command line (CFG-003, CFG-006)
pyspectrometer2 --config config/default.ini --profile lab --set synthetic.seed=7 validate-config

# Run the test suite
pytest
```
