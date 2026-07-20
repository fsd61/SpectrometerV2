# SpectrometerV2

Modular, cross-platform scientific spectrometer application.

> *Think like a physicist. Build like an engineer.*

SpectrometerV2 is a ground-up modernization built around **one platform-neutral
scientific core**, with all OS- and camera-hardware specifics behind adapters.
Linux, Windows, and Raspberry Pi are equal first-class platforms. See the
engineering documents in `Docs/` for the governing Requirements,
Architecture & Design, and Migration Plan.

## Acknowledgements

SpectrometerV2 builds on the original **PySpectrometer2** by **Les Wright**,
whose proven spectral algorithms are preserved as the scientific baseline (see
`Original_Pyspectrometer2/`, tag `baseline-v1.0`). The scientific behavior is
preserved and golden-tested, while the implementation is essentially new — see
`ATTRIBUTION.md` for the full provenance and `NOTICE` for required credits.

## Repository layout

```
src/                  Application sources (flat layout — no wrapper package)
  app/          startup, CLI, orchestration
  config/       INI schema and validation            (CFG-*)
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
config/         default.ini                            (externalized config)
tests/          unit / integration / regression / hardware / platform
Docs/           engineering documents + reference papers
Original_Pyspectrometer2/   Preserved upstream baseline (Les Wright)
Docs/reference/            Preserved historical patch material (reference only)
```

## Status

Working today: configuration and logging services (CLI), and an extracted,
golden-verified scientific core — spectrum extraction, wavelength calibration,
Savitzky–Golay smoothing, peak detection, Gaussian line fitting, FWHM, and SNR —
with an end-to-end analysis pipeline, plus a reproducible synthetic spectrum
generator (Phase 4). Camera adapters (USB, Raspberry Pi, and synthetic) sit
behind a common contract with an acquisition service (Phase 5), and the
application runs headless via a CLI (run / generate-synthetic / analyze /
test-camera / verify-hardware / check-calibration), saving results through a
pluggable persistence sink (Phase 6).

A golden + ground-truth regression suite (`tests/regression/`) pins the baseline
behavior and proves the extracted modules equivalent (Phases 1, 3, 4, 5, 6 & 8). Test suite:
112 tests, installable via `pip install -e .`.

## Usage

```bash
pip install -e .[dev]

# One-time: create your documented config (~/.config/spectrometerv2/config.ini)
spectrometerv2 init-config

# From then on it's auto-loaded — no --config needed
spectrometerv2 validate-config
spectrometerv2 describe-config          # print the documented schema

# Override any value for a single run (CFG-006)
spectrometerv2 --set synthetic.seed=7 validate-config

# Run hardware-free and save a plot
spectrometerv2 --set camera.backend=synthetic --plot generate-synthetic
spectrometerv2 --frames 60 stream        # synthetic waterfall

# Run from source without installing
PYTHONPATH=src python -m app validate-config

# Run the test suite
pytest
```

## Configuration

Configuration is a single INI file. Run `spectrometerv2 init-config` to write a
fully-commented `~/.config/spectrometerv2/config.ini` (generated from the schema,
so every key is documented and defaults are always current). It's auto-discovered
at startup — a project-local `./spectrometerv2.ini` also works, and `--config PATH`
overrides both. `config/config.ini.example` in the repo is a browsable copy of the
same file.

## License

SpectrometerV2 is licensed under the **Apache License 2.0** (see `LICENSE`),
the same license as the upstream PySpectrometer2. Attribution notices are in
`NOTICE`; provenance and credit are detailed in `ATTRIBUTION.md`.
