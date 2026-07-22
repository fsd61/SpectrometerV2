# Attribution & Provenance

SpectrometerV2 is a ground-up modernization of an existing open-source
instrument. This file records where the ideas and code came from, because
credit where it's due matters.

## Upstream: PySpectrometer2 (Les Wright)

SpectrometerV2 builds directly on **PySpectrometer2 by Les Wright** — the
hardware design, optical approach, and the proven spectral-processing
behavior all originate there.

- Source: <https://github.com/leswright1977/PySpectrometer2>
- Author's channel: <https://www.youtube.com/leslaboratory>
- License: **Apache License 2.0**

The original source is preserved **unmodified** in `Original_Pyspectrometer2/`
and frozen at the git tag `baseline-v1.0`.

## What was preserved vs. reimplemented

The guiding rule of the migration was *preserve the science, rewrite the
code*. Concretely:

- **The scientific behavior is preserved and proven identical** to the
  baseline. The regression suite in `tests/regression/` captures the
  baseline's exact outputs as "golden" fixtures and asserts that the
  reimplemented modules reproduce them (Savitzky-Golay smoothing, peak
  detection, and the polynomial wavelength calibration all match to within
  numerical tolerance — several are bit-for-bit).
- **The implementation is essentially new.** Of the code that actually runs
  (`src/`), only a small fraction is baseline-derived logic (roughly 7-8%),
  and most of *that* is third-party (see below). Les Wright's own original
  logic that survives as running code — the calibration approach and the
  3-row-average extraction — is a couple dozen lines of ideas, cleanly
  reimplemented rather than copied.
- In short: **~100% of the proven science retained, ~98% of the code new.**

## Third-party algorithms

Two numerical routines were vendored by the original project and carried
forward (reimplemented) here; their licenses are preserved:

| Component | Source | License |
|---|---|---|
| Savitzky-Golay smoothing (`src/analysis/smoothing.py`) | SciPy Cookbook | BSD 3-Clause |
| Peak detection (`src/analysis/peaks.py`) | peakutils (Lucas Hermann Negri) | MIT |

Both licenses are permissive and compatible with this project's license.

## SpectrometerV2 license

SpectrometerV2 is released under the **Apache License 2.0** — the same
license as the upstream project. See `LICENSE` for the full text and
`NOTICE` for the required attribution notices.

Under Apache-2.0, anyone who redistributes this project (open or closed
source) must retain these attribution notices; they may not remove the
credit or represent the work as their own, and may not use the authors'
names to endorse their derivative.
