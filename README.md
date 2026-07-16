# SpectrometerV2

Modular, cross-platform scientific spectrometer application.

> *Think like a physicist. Build like an engineer.*

SpectrometerV2 is a ground-up modernization built around **one platform-neutral
scientific core**, with all OS- and camera-hardware specifics behind adapters.
Linux, Windows, and Raspberry Pi are equal first-class platforms. See the
Rev 1.2 engineering documents in `Docs/` for the governing Requirements,
Architecture & Design, and Migration Plan.

## Acknowledgements

SpectrometerV2 builds on the original **PySpectrometer2** by **Les Wright**,
whose proven spectral algorithms are preserved as the scientific baseline (see
`Original_Pyspectrometer2/`, tag `baseline-v1.0`). Full credit and licensing
attribution will accompany the first public release.

## Repository layout

```
src/                  Application sources (flat layout — no wrapper package)
  app/          startup, CLI, orchestration
  config/       INI schema, validation, profiles      (CFG-*)
  platforms/    platform-specific services            (PLAT-*)
  cameras/      camera contract + adapters (USB, Pi)   (HW-*)
  acquisition/  frame capture + acquisition metadata
  processing/   spectrum extraction + shared Spectrum object
  calibration/  wavelength calibration
  analysis/     peak detection, fitting, FWHM, SNR
  synthetic/    reproducible synthetic spectra         (SYN-*)
  data/         persistence + metadata                 (DATA-*)
  ui/           GUI + plotting
  errors.py         application exception hierarchy
  logging_setup.py  structured rotating logging        (LOG-*)
config/         default.ini + profiles/                (externalized config)
tests/          unit / integration / regression / hardware / platform
Docs/           Rev 1.2 engineering documents + reference papers
Original_Pyspectrometer2/   Preserved upstream baseline (Les Wright)
Patch_-_Vertical_Slice/     Preserved in-progress patch material
Patch_-_Wtx_+_SA/           Preserved in-progress patch material
```

## Status

Sprint 1 skeleton. Working today: the configuration service and logging
service, wired into a CLI. Scientific modules, camera adapters, and the
synthetic generator are stubs to be filled in per the Migration Plan phases.

## Usage

```bash
pip install -e .[dev]

# Validate configuration (CLI-004)
spectrometerv2 --config config/default.ini validate-config

# Print the documented configuration schema (CFG-004)
spectrometerv2 describe-config

# Overlay a profile and override a value at the command line (CFG-003, CFG-006)
spectrometerv2 --config config/default.ini --profile lab --set synthetic.seed=7 validate-config

# Run from source without installing
PYTHONPATH=src python -m app validate-config

# Run the test suite
pytest
```
