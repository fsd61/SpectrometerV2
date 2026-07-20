"""
test_specFunctions.py
Synthetic test suite for the specFunctions analysis extensions.

Test structure mirrors DiGennaro & Cowburn (J. Magn. Reson. 96, 582-588, 1992):
  - Single peak (noise-free)
  - Five peaks  (noise-free)
  - Seven peaks (noise-free)
  - Four peaks  (SNR ~5:1)

Each test verifies that simulated_annealing() recovers the known input
parameters within a defined tolerance.  FFT and wavelet smoke-tests are
also included.

Usage:
    python3 test_specFunctions.py
"""

import sys, os
os.environ['MPLBACKEND'] = 'Agg'
sys.path.insert(0, '/mnt/user-data/outputs')

import numpy as np
from specFunctions import fft_spectrum, wavelet_transform, simulated_annealing, plot_analysis

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'
results = []

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def make_spectrum(wavelengths, peaks, noise_sigma=0.0, seed=0):
    """
    Build a synthetic spectrum from a list of Gaussian peaks.
    peaks: list of (amplitude, center_nm, sigma_nm)
    Returns intensity array.
    """
    rng = np.random.default_rng(seed)
    y = np.zeros_like(wavelengths, dtype=float)
    for amp, center, sigma in peaks:
        y += amp * np.exp(-((wavelengths - center) ** 2) / (2 * sigma ** 2))
    if noise_sigma > 0:
        y += rng.normal(0, noise_sigma, len(y))
    return y


def multi_peak_residual(params, wavelengths, y_data, n_peaks):
    """
    Objective: sum-of-squared residuals for n_peaks Gaussians.
    params layout: [amp0, center0, sigma0, amp1, center1, sigma1, ...]
    """
    model = np.zeros_like(y_data)
    for i in range(n_peaks):
        amp, center, sigma = params[3*i], params[3*i+1], params[3*i+2]
        model += amp * np.exp(-((wavelengths - center) ** 2) / (2 * sigma ** 2))
    return float(np.sum((y_data - model) ** 2))


def check(label, recovered, expected, tol):
    ok = abs(recovered - expected) <= tol
    status = PASS if ok else FAIL
    print(f"  {status}  {label}: expected={expected:.3f}  "
          f"got={recovered:.3f}  diff={abs(recovered-expected):.3f}  tol={tol}")
    results.append(ok)
    return ok


# Wavelength axis: 800 pixels, 380-750 nm (matches PySpectrometer2 layout)
WL = np.linspace(380, 750, 800)

# ------------------------------------------------------------------ #
# TEST 1: Single peak, noise-free
# ------------------------------------------------------------------ #
print("\n=== Test 1: Single peak (noise-free) ===")
TRUE_1 = [(1.0, 450.0, 15.0)]
y1 = make_spectrum(WL, TRUE_1)

def obj1(p): return multi_peak_residual(p, WL, y1, 1)

r1 = simulated_annealing(
    obj1, x0=[0.8, 440.0, 20.0],
    schedule='medium', T0=None, n_components=1,
    bounds=[(0,5),(380,750),(1,80)],
    tol=1e-5, random_seed=1,
)
print(f"  cycles={r1['cycles']}  quenched={r1['quenched']}  "
      f"converged={r1['converged']}  T0={r1['T0']:.3g}")
check("amplitude", r1['x'][0], 1.0,   0.05)
check("center nm", r1['x'][1], 450.0, 1.0)
check("sigma nm",  r1['x'][2], 15.0,  1.0)

# ------------------------------------------------------------------ #
# TEST 2: Five peaks, noise-free
# ------------------------------------------------------------------ #
print("\n=== Test 2: Five peaks (noise-free) ===")
TRUE_2 = [
    (5.0, 400.0, 8.0),
    (3.0, 450.0, 6.0),
    (3.0, 500.0, 7.0),
    (4.0, 580.0, 9.0),
    (5.0, 650.0, 8.0),
]
y2 = make_spectrum(WL, TRUE_2)

def obj2(p): return multi_peak_residual(p, WL, y2, 5)

# Initial guess: deliberately offset from truth
x0_2 = [4.0,395,10, 2.5,445,8, 2.5,495,9, 3.5,575,11, 4.5,645,10]
bounds_2 = [(0,10),(380,750),(1,50)] * 5

r2 = simulated_annealing(
    obj2, x0=x0_2,
    schedule='medium', T0=None, n_components=5,
    bounds=bounds_2,
    tol=1e-5, random_seed=2,
)
print(f"  cycles={r2['cycles']}  quenched={r2['quenched']}  "
      f"converged={r2['converged']}  T0={r2['T0']:.3g}")
for i,(amp,cen,sig) in enumerate(TRUE_2):
    check(f"peak{i+1} amplitude", r2['x'][3*i],   amp,  0.3)
    check(f"peak{i+1} center nm", r2['x'][3*i+1], cen,  2.0)
    check(f"peak{i+1} sigma nm",  r2['x'][3*i+2], sig,  2.0)

# ------------------------------------------------------------------ #
# TEST 3: Seven peaks, noise-free
# ------------------------------------------------------------------ #
print("\n=== Test 3: Seven peaks (noise-free) ===")
TRUE_3 = [
    (5.0, 400.0, 8.0),
    (3.0, 430.0, 6.0),
    (3.0, 480.0, 7.0),
    (4.0, 520.0, 8.0),
    (5.0, 570.0, 7.0),
    (4.0, 620.0, 9.0),
    (3.0, 680.0, 8.0),
]
y3 = make_spectrum(WL, TRUE_3)

def obj3(p): return multi_peak_residual(p, WL, y3, 7)

x0_3 = [4,395,10, 2.5,425,8, 2.5,475,9, 3.5,515,10,
         4.5,565,9, 3.5,615,11, 2.5,675,10]
bounds_3 = [(0,10),(380,750),(1,50)] * 7

r3 = simulated_annealing(
    obj3, x0=x0_3,
    schedule='slow', T0=None, n_components=7,
    bounds=bounds_3,
    tol=1e-5, random_seed=3,
)
print(f"  cycles={r3['cycles']}  quenched={r3['quenched']}  "
      f"converged={r3['converged']}  T0={r3['T0']:.3g}")
for i,(amp,cen,sig) in enumerate(TRUE_3):
    check(f"peak{i+1} amplitude", r3['x'][3*i],   amp,  0.5)
    check(f"peak{i+1} center nm", r3['x'][3*i+1], cen,  2.0)
    check(f"peak{i+1} sigma nm",  r3['x'][3*i+2], sig,  2.0)

# ------------------------------------------------------------------ #
# TEST 4: Four peaks, SNR ~5:1  (matches paper Table 2)
# ------------------------------------------------------------------ #
print("\n=== Test 4: Four peaks (SNR ~5:1) ===")
TRUE_4 = [
    (1.0, 420.0, 12.0),
    (2.0, 490.0, 12.0),
    (1.0, 560.0, 15.0),
    (2.0, 630.0, 16.0),
]
peak_max = max(a for a,c,s in TRUE_4)
noise_sigma = peak_max / 5.0   # SNR = 5:1
y4 = make_spectrum(WL, TRUE_4, noise_sigma=noise_sigma, seed=42)

def obj4(p): return multi_peak_residual(p, WL, y4, 4)

x0_4 = [0.8,415,15, 1.7,485,14, 0.8,555,17, 1.7,625,18]
bounds_4 = [(0,5),(380,750),(1,60)] * 4

r4 = simulated_annealing(
    obj4, x0=x0_4,
    schedule='slow', T0=None, n_components=4,
    bounds=bounds_4,
    tol=1e-5, random_seed=4,
)
print(f"  cycles={r4['cycles']}  quenched={r4['quenched']}  "
      f"converged={r4['converged']}  T0={r4['T0']:.3g}")
# Looser tolerance at SNR 5:1 — noise shifts the apparent peak
for i,(amp,cen,sig) in enumerate(TRUE_4):
    check(f"peak{i+1} amplitude", r4['x'][3*i],   amp,  0.4)
    check(f"peak{i+1} center nm", r4['x'][3*i+1], cen,  4.0)
    check(f"peak{i+1} sigma nm",  r4['x'][3*i+2], sig,  4.0)

# ------------------------------------------------------------------ #
# TEST 5: FFT smoke test
# ------------------------------------------------------------------ #
print("\n=== Test 5: FFT ===")
fft = fft_spectrum(y2)
fft_ok = (
    len(fft['freqs']) == len(fft['magnitudes']) and
    fft['freqs'][0] == 0.0 and
    len(fft['full_fft']) == len(fft['freqs'])
)
status = PASS if fft_ok else FAIL
print(f"  {status}  FFT shape/DC checks")
results.append(fft_ok)

# ------------------------------------------------------------------ #
# TEST 6: Wavelet smoke test
# ------------------------------------------------------------------ #
print("\n=== Test 6: Wavelet ===")
wt = wavelet_transform(y2, wavelet='db4', level=4)
wt_ok = (
    len(wt['details']) == 4 and
    len(wt['approximation']) > 0 and
    wt['wavelet'] == 'db4' and
    wt['level'] == 4
)
status = PASS if wt_ok else FAIL
print(f"  {status}  Wavelet decomposition structure")
results.append(wt_ok)

# ------------------------------------------------------------------ #
# TEST 7: Plot output
# ------------------------------------------------------------------ #
print("\n=== Test 7: Plot ===")
try:
    fig = plot_analysis(
        WL, y2,
        fft_result=fft, wavelet_result=wt, sa_result=r2,
        title='Test Suite Plot',
        save_path='/home/claude/test_suite_plot.png',
    )
    plot_ok = fig is not None
except Exception as e:
    plot_ok = False
    print(f"  Plot error: {e}")
status = PASS if plot_ok else FAIL
print(f"  {status}  plot_analysis() produced a figure")
results.append(plot_ok)

# ------------------------------------------------------------------ #
# Summary
# ------------------------------------------------------------------ #
total  = len(results)
passed = sum(results)
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("All tests passed.")
else:
    print(f"{total - passed} test(s) FAILED.")
sys.exit(0 if passed == total else 1)
