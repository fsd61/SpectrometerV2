# Regression / golden tests (Migration Plan Phase 1)

These tests **preserve proven baseline behavior** before the scientific core is
extracted, so the migrated code can be shown to be numerically equivalent.

## What's here

- `_baseline.py` — loads Les Wright's original `specFunctions.py`
  (`Original_Pyspectrometer2/`, tag `baseline-v1.0`) and a **deterministic**
  synthetic-spectrum generator (NumPy PCG64 `default_rng`, version-stable).
- `generate_golden.py` — regenerates `golden/*.json` from the baseline.
- `golden/` — committed expected outputs (savgol, peaks, wavelength→RGB,
  calibration, graticule).
- `test_baseline_characterization.py` — **characterization**: re-run the
  baseline and assert it still reproduces the golden snapshots (guards against
  accidental drift; later the migrated modules are checked against the same
  files).
- `test_synthetic_recovery.py` — **ground truth**: peak-center recovery,
  amplitude ordering, FWHM self-check, and an SNR sanity relationship
  (the template the new `analysis` module must satisfy — TEST-002).

## Regenerating golden data

Only when a change to the baseline behavior is intentional:

```bash
PYTHONPATH=tests python tests/regression/generate_golden.py
```

## Migration use

When a function is ported into `src/analysis`, `src/calibration`, or
`src/processing`, add an assertion that the **new** implementation reproduces the
same `golden/*.json` within tolerance (Gate C).
