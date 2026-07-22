"""Integration: synthetic generation flows through the same analysis pipeline
(SYN-008; TEST-002 recovery)."""

import pytest

from synthetic.generator import SyntheticSpectrumSpec, generate
from analysis.pipeline import analyze

LINES = [404.66, 435.83, 546.07, 611.60]
FWHMS = [2.0, 1.5, 3.0, 2.0]
AMPS = [200.0, 120.0, 180.0, 90.0]


def test_generate_then_analyze_recovers_lines():
    spec = SyntheticSpectrumSpec(
        center_wavelengths=LINES, amplitudes=AMPS, per_line_fwhm=FWHMS,
        wavelength_min=380, wavelength_max=750, sample_interval=0.5,
        snr=200.0, baseline=5.0, seed=42,
    )
    s = generate(spec)
    res = analyze(s.intensities, wavelengths=s.wavelengths,
                  peak_thres=0.1, peak_min_dist=10, measure=True, measure_window=20)

    recovered = sorted(p.wavelength for p in res.peaks)
    assert len(recovered) == len(LINES)
    for center in LINES:
        assert any(abs(g - center) <= 1.0 for g in recovered), f"missed {center}: {recovered}"

    for peak in res.peaks:
        i = min(range(len(LINES)), key=lambda k: abs(LINES[k] - peak.wavelength))
        assert peak.fwhm_nm == pytest.approx(FWHMS[i], rel=0.15)
        assert peak.snr > 0
