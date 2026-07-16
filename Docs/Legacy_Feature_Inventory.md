# Legacy Feature Inventory

**Project:** SpectrometerV2  **Status:** working engineering artifact
**Date:** 2026-07-16  **Maps to:** Migration Plan Phase 0 (Baseline Preservation)
and the First-Sprint checklist item *"Inventory current features and hard-coded
parameters."*

Purpose: catalog everything the baseline code (Les Wright's PySpectrometer2,
preserved under `Original_Pyspectrometer2/`, tag `baseline-v1.0`) actually does,
so no proven behavior is lost during migration. Line numbers refer to the
baseline files.

---

## 1. Source files

| File | Lines | Role |
|---|---|---|
| `Original_Pyspectrometer2/src/PySpectrometer2-USB-v1.0.py` | 457 | Main app for USB/webcam cameras (OpenCV + V4L). |
| `Original_Pyspectrometer2/src/PySpectrometer2-Picam2-v1.0.py` | 466 | Main app for the Raspberry Pi camera (Picamera2). Near-duplicate of the USB app plus gain control. |
| `Original_Pyspectrometer2/src/specFunctions.py` | 464 | Shared scientific + UI helper library. |
| `Patch_-_Wtx_+_SA/specFunctions.py` | 999 | Superset of the above adding FFT, wavelet denoising, simulated-annealing fitting, and plotting. |
| `Patch_-_Vertical_Slice/compare_slices*.py` + `gemini-code-*` | — | Experimental vertical-slice extraction studies (AI-assisted); not part of the shipped app. |

The two main scripts are ~90% identical: they share the same UI, processing
loop, keybindings, and helper calls, differing only in the camera-acquisition
block (and the Picamera2 gain keys). **This duplication is the single strongest
argument for the camera-abstraction layer (HW-001..HW-004).**

## 2. Dependencies

- **Baseline runtime:** `opencv-python` (`cv2`), `numpy`, plus stdlib
  `argparse`, `base64`, `time`, `math`.
- **Picamera2 app:** additionally `picamera2.Picamera2` (Raspberry Pi only).
- **Vendored code:** `peakIndexes()` is copied from *peakutils* (MIT);
  `savitzky_golay()` is from the SciPy cookbook (uses `math.factorial`).
- **Wtx+SA patch adds (optional, imported lazily inside functions):** `scipy`,
  `pywt` (wavelets), `matplotlib` (plotting), plus stdlib `random`. These are
  **not** baseline dependencies and should be gated behind an optional install.

## 3. Command-line interface (baseline `argparse`)

| Option | Type / default | Meaning |
|---|---|---|
| `--device` | int, `0` | V4L video device number (USB app only; `/dev/video<N>`). |
| `--fps` | int, `30` | Requested frame rate. |
| `--fullscreen` | flag | Fullscreen, native 800×480 (mutually exclusive with `--waterfall`). |
| `--waterfall` | flag | Enable the scrolling waterfall view (windowed only). |

These map onto the new `app/cli.py` + `config/` (CLI-001..004, CFG-*).

## 4. Camera acquisition

**USB (`cv2`):** `cv2.VideoCapture('/dev/video'+dev, cv2.CAP_V4L)`, then sets
`CAP_PROP_FRAME_WIDTH=800`, `CAP_PROP_FRAME_HEIGHT=600`, `CAP_PROP_FPS=fps`.
The `/dev/video` path and `CAP_V4L` backend are **Linux-only** — a concrete
gap for Windows first-class support (PLAT-002).

**Picamera2:** `create_video_configuration(main={"format":'RGB888',
"size":(800,600)}, controls={"FrameDurationLimits":(33333,33333)})` (~30 fps).
Analogue gain is adjustable at runtime via keys **t/g** (`picamGain`, default
`10.0`, clamped 0–50). Brightness/Contrast controls exist but are commented out.

## 5. Processing / science pipeline

1. Grab frame → crop a horizontal band about the vertical centre
   (`y = frameHeight/2 − 40`); **3-row pixel averaging** produces the 1-D
   `intensity` array of length `frameWidth` (800).
2. **Savitzky–Golay smoothing** (`savitzky_golay`, window/param `savpoly`,
   default 7, adjustable 0–15 via o/l).
3. **Peak detection** (`peakIndexes`, `thres`/`min_dist`) with a **peak-hold**
   mode (key h) that latches maxima.
4. **Wavelength calibration** (`readcal`/`writecal`, file `caldata.txt` in CWD):
   manual click-calibration on known emission lines; **2nd-order polynomial fit
   for exactly 3 points, 3rd-order for more** (`np.polyfit`). Produces the
   pixel→nm `wavelengthData` array.
5. **Graticule** (`generateGraticule`) computes 10 nm (`tens`) and 50 nm
   (`fifties`) tick positions across the calibrated axis.
6. **Colour mapping** (`wavelength_to_rgb`, 380–750 nm) tints the trace and
   waterfall.

Helper functions in `specFunctions.py`: `wavelength_to_rgb` (L32),
`savitzky_golay` (L89), `peakIndexes` (L147), `readcal` (L241), `writecal`
(L373), `generateGraticule` (L401), plus an embedded base64 PNG `background`.

## 6. Display & interaction

Two OpenCV windows: **"PySpectrometer 2 - Spectrograph"** and **"...- Waterfall"**.
Composite window height `stackHeight = 320 (graph) + 80 (preview) + 80
(messages) = 480`. Waterfall buffer `np.zeros([320, 800, 3])` scrolls intensity
as a heat-map. Fullscreen targets 800×480 (common RPi LCD).

**Keybindings (USB):**

| Key | Action | Key | Action |
|---|---|---|---|
| `q` | quit | `p` | record-pixels cursor toggle |
| `h` | peak-hold toggle | `o`/`l` | Sav–Gol param up/down (0–15) |
| `s` | snapshot (PNG + CSV) | `i`/`k` | peak min-distance up/down (0–100) |
| `c` | calibrate (write+read cal) | `u`/`j` | label threshold up/down (0–100) |
| `x` | clear calibration clicks | `m` | measurement cursor toggle |

Picamera2 app adds **t/g** (gain up/down). Mouse (`handle_mouse`) records
calibration click points and cursor position.

## 7. Persistence / output formats

`snapshot()` writes to the current working directory:
`spectrum-<timestamp>.png`, `waterfall-<timestamp>.png` (if enabled), and
`Spectrum-<timestamp>.csv` with header `Wavelength,Intensity` (CRLF).
Calibration persists as `caldata.txt` (pixel/wavelength pairs, no metadata).

## 8. Hard-coded parameters to externalize (→ `config/`, CFG-*)

| Parameter | Baseline value | Notes |
|---|---|---|
| frame width / height | 800 / 600 | sensor + graph width |
| fps | 30 | |
| crop origin / averaging | `H/2 − 40`, 3 rows | vertical-slice extraction |
| waterfall height / stack height | 320 / 480 | |
| `savpoly` | 7 (0–15) | Sav–Gol smoothing |
| `mindist` | 50 (0–100) | peak spacing |
| `thresh` | 20 (0–100) | peak-label threshold |
| `picamGain` | 10.0 (0–50) | Picamera2 only |
| FrameDurationLimits | 33333 µs | Picamera2 ~30 fps |
| calibration file | `caldata.txt` (CWD) | fixed name/location |
| window titles | "PySpectrometer 2 - ..." | |
| colour range | 380–750 nm | `wavelength_to_rgb` |
| device path | `/dev/video<N>`, `CAP_V4L` | Linux-only |

## 9. Known limitations & migration risks

- **Linux/V4L coupling** in the USB app (device path + backend) blocks Windows
  parity (PLAT-002).
- **Duplicated main scripts** (USB vs Picamera2) with copy-pasted UI/loop →
  resolve via the camera contract + one shared app core.
- **Intermixed concerns:** acquisition, science, and OpenCV UI live in one
  module-level script with global state → separate per the target architecture.
- **No config, no logging, no tests:** parameters are hard-coded or key-adjusted
  at runtime and never persisted; diagnostics via `print()` → CFG-*, LOG-*.
- **Calibration/output** land in CWD with no metadata and inconsistent casing
  (`spectrum-*.png` vs `Spectrum-*.csv`) → DATA-001/002.
- **No synthetic generator in the baseline** — the SYN-* requirements are new
  capability, though the Wtx+SA patch's analysis functions inform them.

## 10. Wtx+SA patch — candidate advanced analysis (optional)

Superset `specFunctions.py` (999 lines) keeps the six baseline functions
unchanged and adds:

- `fft_spectrum(intensity, sample_spacing)` — FFT of the spectrum (L416).
- `wavelet_transform(intensity, wavelet='db4', level=4)` — `pywt` wavelet
  decomposition/denoise (L450).
- `simulated_annealing(...)` + `_tune_T0(...)` — global optimiser for
  multi-component line fitting (L509/L556).
- `plot_analysis(...)` — matplotlib figure combining spectrum/FFT/wavelet/SA
  results (L798).

These belong in `analysis/` as **optional, dependency-gated** features
(`scipy`, `pywt`, `matplotlib`), not in the core runtime.

## 11. Mapping to target modules

| Legacy behavior | Target module | Requirements |
|---|---|---|
| USB / Picamera2 capture | `cameras/` (+`acquisition/`) | HW-002, HW-003, PLAT-005 |
| crop + 3-row average → 1-D spectrum | `processing/` (`Spectrum`) | — |
| Sav–Gol, peak detect, FWHM/SNR | `analysis/` | TEST-002 |
| polynomial calibration, `caldata.txt` | `calibration/` | DATA-002 |
| `wavelength_to_rgb`, graticule, waterfall, windows, keys | `ui/` | — |
| snapshots, CSV, calibration files | `data/` | DATA-001/002 |
| argparse, runtime params | `app/cli.py`, `config/` | CLI-*, CFG-* |
| FFT / wavelet / SA / plotting (patch) | `analysis/` (optional deps) | SYN-007 (profiles) |

---
*Inventory compiled from the baseline sources at tag `baseline-v1.0`. Update as
extraction proceeds (Migration Plan Phases 3–4).*
