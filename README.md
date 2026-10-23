# SpectrometerV2

Calibrated, tested software for DIY diffraction spectrometers, on Raspberry Pi,
Windows, and Linux. A ground-up modernization of Les Wright's PySpectrometer2.

> *Think like a physicist. Build like an engineer.*

![SpectrometerV2 main window: live spectrum with detected peaks, a scrolling waterfall, and the peak table](Docs/images/main-window.png)

## What it does

- **Live spectrum and waterfall** with automatic peak detection and a peak
  table you can read wavelengths straight off.
- **Wavelength calibration** from known reference lines (click peaks to pick
  points), with the calibration recorded alongside every measurement.
- **Line analysis:** Savitzky-Golay smoothing, Gaussian peak fits, FWHM, and SNR.
- **More signal from the same frame:** average the whole slit image instead of
  3 rows, for up to about 10x the signal-to-noise of PySpectrometer2
  ([details](#more-signal-from-the-same-frame)).
- **Built-in signal generator**, so you can learn the software, tune settings,
  and check the analysis against known answers with no hardware at all.
- **Logging you can query:** CSV by default, plus optional SQLite and InfluxDB
  (for Grafana).
- **Same keys as PySpectrometer2**, and its scientific results are preserved,
  pinned by golden regression tests.
- **349 automated tests.** Windows, Linux, and Raspberry Pi are all first-class.

## Try it in two minutes, no hardware needed

Clone the repository (or download the latest zip from
[Releases](https://github.com/fsd61/SpectrometerV2/releases) and unzip it), then:

```bash
git clone https://github.com/fsd61/SpectrometerV2.git
cd SpectrometerV2
python -m venv .venv            # python3 on Linux
# Windows: .venv\Scripts\activate      Linux: source .venv/bin/activate
pip install -e ".[gui]"
spectrometerv2 --set camera.backend=synthetic gui
```

The window opens in **[SIMULATED]** mode with a reference spectrum. Use the
**Synthetic source** tab to add, move, and reshape peaks, change the noise
level, or let the peaks drift, and watch the analysis follow.

<p>
  <img src="Docs/images/synthetic-source.png" width="49%" alt="Synthetic source panel: editable peak list with wavelength, amplitude and FWHM, plus SNR, baseline and drift settings">
  <img src="Docs/images/keyboard-shortcuts.png" width="49%" alt="Keyboard shortcuts carried over from PySpectrometer2">
</p>

Ready for a real camera? [INSTALL.md](INSTALL.md) covers USB cameras, the
Raspberry Pi camera, and platform-specific setup.

## What sets it apart

### More signal from the same frame

PySpectrometer2 builds each spectrum from 3 rows of the camera image, but the
slit image is usually hundreds of rows tall. SpectrometerV2 can average as many
rows as the slit image covers. Random noise falls as 1/sqrt(rows), so the
signal-to-noise ratio rises with the band:

| Rows averaged          | Signal-to-noise vs PySpectrometer2 |
|-----------------------:|-----------------------------------:|
| 3 (PySpectrometer2)    | 1x                                 |
| 25                     | 2.9x                               |
| 81                     | 5.2x                               |
| 401                    | 11.4x                              |

*Simulated: 1280x800 8-bit frames, 3 counts of per-pixel noise, a 401-row slit
image. Re-run with your own assumptions: `python scripts/measure_slice_height.py --help`.*

```ini
[processing]
# Odd; keep the whole band inside the bright slit image.
slice_height = 301
# Keep the fraction; truncating to whole counts would cap the gain near 2.6x.
slice_precision = float
```

A taller band does not improve resolution. If the slit image is tilted relative
to the pixel rows, lines broaden as the band grows (about 6% for a 2-pixel tilt
across 401 rows). The default stays at PySpectrometer2's 3 rows.

### Simulated annealing line fitting

Adapted from DiGennaro & Cowburn, "Parametric Estimation of Time-Domain NMR
Signals Using Simulated Annealing", *J. Magn. Reson.* 96, 582–588 (1992): a
global optimizer for fitting overlapping lines, with an auto-tuned starting
temperature, Markov chains scaled to the number of lines, a quench to fast
final convergence, and seeded, reproducible runs. Primer:
[Docs/simulated_annealing_primer.pdf](Docs/simulated_annealing_primer.pdf).

### Wavelet decomposition

Multi-level discrete wavelet transforms (Daubechies, symlet, and Coiflet
families), the basis for separating sharp lines from noise and slow baseline.
Primer: [Docs/wavelet_transforms_primer.pdf](Docs/wavelet_transforms_primer.pdf).

Simulated annealing and wavelets are in the `analysis` package, tested and
configurable; their controls in the GUI are next.

## Design

SpectrometerV2 is built around **one platform-neutral
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
  data/         persistence: locked core schema, CSV / SQLite / InfluxDB
                sinks, user field manifest             (DATA-*)
  ui/           GUI + plotting
  errors.py         application exception hierarchy
  logging_setup.py  structured rotating logging        (LOG-*)
config/         config.ini (+ alternates)              (externalized config)
tests/          unit / integration / regression / hardware / platform
Docs/           engineering documents + reference papers
Original_Pyspectrometer2/   Preserved upstream baseline (Les Wright)
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

Persistence writes CSV by default and can additionally tee to **SQLite** (the
queryable system of record: spectrum arrays, calibration records, full
provenance) and **InfluxDB** (scalar telemetry for Grafana). Both are off by
default. The core schema is locked — capture identity, backend provenance and
calibration fingerprint are fixed and cannot be overridden — while anything else
you want to collect is declared in a small INI manifest that applies to both
stores at once. See `config/user_fields.ini.example`.

A golden + ground-truth regression suite (`tests/regression/`) pins the baseline
behavior and proves the extracted modules equivalent (Phases 1, 3, 4, 5, 6 & 8). Test suite:
349 tests, installable via `pip install -e .`.

## Usage

```bash
pip install -e .[dev]

# One-time: create your documented config (config/config.ini)
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

Everything lives in the project directory, so the whole thing is self-contained
and movable. Configuration is a single INI file in the project's `config/`
folder. Run `spectrometerv2 init-config` to write a fully-commented
`config/config.ini` (generated from the schema, so every key is documented). It's
auto-discovered at startup — resolved from the project root, so it works from any
subdirectory — and `--config PATH` overrides it. Keep alternate complete configs
alongside it (e.g. `config/lab.ini`) and select one with `--config config/lab.ini`.
`config/config.ini.example` is a browsable copy.

## Feedback

Tried it? Feedback of any kind is welcome: post in
[Discussions](https://github.com/fsd61/SpectrometerV2/discussions), or open an
[issue](https://github.com/fsd61/SpectrometerV2/issues) if something breaks.

## License

SpectrometerV2 is licensed under the **Apache License 2.0** (see `LICENSE`),
the same license as the upstream PySpectrometer2. Attribution notices are in
`NOTICE`; provenance and credit are detailed in `ATTRIBUTION.md`.
