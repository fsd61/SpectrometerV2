"""Scientific analysis: peak detection, line fitting, FWHM, SNR estimation.

Platform-neutral algorithms consuming the shared Spectrum object. Extracted from
the baseline and verified against golden and synthetic ground-truth data
(Migration Plan Phase 3; TEST-002).
"""

from .peaks import peak_indexes
from .smoothing import savitzky_golay
from .measurements import (
    GaussianFit,
    estimate_noise,
    estimate_snr,
    gaussian_fit,
    half_max_fwhm,
)
from .pipeline import Peak, SpectralAnalysis, analyze
from .transforms import FftResult, WaveletResult, fft_spectrum, wavelet_transform
from .annealing import (
    AnnealingResult,
    gaussian_sum,
    simulated_annealing,
    sum_of_squares_objective,
)

__all__ = [
    "peak_indexes", "savitzky_golay",
    "GaussianFit", "gaussian_fit", "half_max_fwhm", "estimate_noise", "estimate_snr",
    "Peak", "SpectralAnalysis", "analyze",
    "FftResult", "WaveletResult", "fft_spectrum", "wavelet_transform",
    "AnnealingResult", "simulated_annealing", "gaussian_sum", "sum_of_squares_objective",
]
